from flair_api import make_client
import time
import pickle
import os.path
import sys
import shelve
import math
from datetime import datetime
import pytz
from six.moves import input
from pyecobee import *
import requests
def set_state(vent, val):
  global vent_state
  print("update",vent.attributes['name'],"to",val)
  vent_state[vent.attributes['name']] = val

def get_state(vent):
  global vent_state
  if vent.attributes['name'] in vent_state:
    return vent_state[vent.attributes['name']] 
  return vent.attributes['percent-open']

def persist_to_shelf(file_name, ecobee_service):
    pyecobee_db = shelve.open(file_name, protocol=2)
    pyecobee_db[ecobee_service.thermostat_name] = ecobee_service
    pyecobee_db.close()

def inake_vent_temp_bad(room, mode,ctemp):
    global bad_vent,bad_time,temp_at_intake_start
    if mode == "cool":
        # If the temprature has gone _up_, then this isn't working out...
        if room.attributes['name'] in temp_at_intake_start:
            if temp_at_intake_start[room.attributes['name']] < (ctemp-1.0):
                print("Intake override because",room.attributes['name'],"is above temp when the intake started",temp_at_intake_start[room.attributes['name']],"initial vs ",ctemp,"now")
                bad_vent = True
                return True
        # Double check if this is actually working...
        for vent in room.get_rel('vents'):
            duct = vent.get_rel('current-reading').attributes['duct-temperature-c']
            print(bad_intake_time, intake_blackout)
            if (duct > (ctemp - intake_duct_toll) and intake_time > intake_min_time):
                bad_vent = True
                print("Intake override because",vent.attributes['name'],"is above temp")
                return True
    else:
        # If the temprature has gone _up_, then this isn't working out...
        if room.attributes['name'] in temp_at_intake_start:
            if temp_at_intake_start[room.attributes['name']] > (ctemp+1.0):
                print("Intake override because",room.attributes['name'],"is below temp when the intake started",temp_at_intake_start[room.attributes['name']],"initial vs ",ctemp,"now")
                bad_vent = True
                return True
        # Double check if this is actually working...
        for vent in room.get_rel('vents'):
            duct = vent.get_rel('current-reading').attributes['duct-temperature-c']
            if duct < (ctemp + intake_duct_toll) and intake_time > intake_min_time:
                bad_vent = True
                print("Intake override because",vent.attributes['name'],"is below temp")
                return True
    if bad_intake_time < intake_blackout:
        if intake_time > intake_min_time:
            print("intake override due to blackout time - time remaining",intake_blackout - bad_intake_time)
            bad_time = True
        return True
    return False
        

def refresh_tokens(ecobee_service):
    token_response = ecobee_service.refresh_tokens()
    print('TokenResponse returned from ecobee_service.refresh_tokens():\n{0}'.format(
        token_response.pretty_format()))

    persist_to_shelf('pyecobee_db', ecobee_service)


def request_tokens(ecobee_service):
    token_response = ecobee_service.request_tokens()
    print('TokenResponse returned from ecobee_service.request_tokens():\n{0}'.format(
        token_response.pretty_format()))

    persist_to_shelf('pyecobee_db', ecobee_service)


def authorize(ecobee_service):
    authorize_response = ecobee_service.authorize()
    print('AutorizeResponse returned from ecobee_service.authorize():\n{0}'.format(
        authorize_response.pretty_format()))

    persist_to_shelf('pyecobee_db', ecobee_service)

    print('Please goto ecobee.com, login to the web portal and click on the settings tab. Ensure the My '
                'Apps widget is enabled. If it is not click on the My Apps option in the menu on the left. In the '
                'My Apps widget paste "{0}" and in the textbox labelled "Enter your 4 digit pin to '
                'install your third party app" and then click "Install App". The next screen will display any '
                'permissions the app requires and will ask you to click "Authorize" to add the application.\n\n'
                'After completing this step please hit "Enter" to continue.'.format(
        authorize_response.ecobee_pin))
    input()


from secrets import *
from settings import *
from setpoints import *

if os.path.exists("last_bad_intake.pic"):
  r = open("last_bad_intake.pic", "rb")
  last_bad_intake = pickle.load(r)
  r.close()
else:
  last_bad_intake = time.time()

if os.path.exists("last_intake.pic"):
  r = open("last_intake.pic", "rb")
  last_intake = pickle.load(r)
  r.close()
else:
  last_intake = time.time()

if os.path.exists("temp_at_intake_start.pic"):
  r = open("temp_at_intake_start.pic", "rb")
  temp_at_intake_start = pickle.load(r)
  r.close()
else:
  temp_at_intake_start = {}


room_temps = {}

intake_time = time.time() - last_intake
bad_intake_time = time.time() - last_bad_intake

client = make_client(client_id, client_secret, 'https://api.flair.co/')

# retrieve a list of structures available to this account
structures = client.get('structures')
mode = structures[0].attributes['structure-heat-cool-mode']
print("Mode is",mode)

rooms = client.get('rooms')
vent_state = {}

cooling = False
heating = False
parking = False
delta = 0.0
intake_temp = 999
# If using an intake room, find that first since earlier rooms
# may need it
if use_intake_room:
  for room in rooms:
    if room.attributes['name'] == intake_room:
      intake_temp = room.attributes['current-temperature-c']
      print("Found intake room!",intake_temp)

rcount = 0
force_park = False
max_delta = -999
min_delta = 999
delta_list = []
actual_vent_count = 0
need_force_cool = False
need_force_heat = False
any_manual = False
can_use_intake = False
bad_vent = False
bad_time = False
disable_heat_due_to_overload = False
celcius_heat_cutoff = max_vent_temp
if switch_is_f:
  celcius_heat_cutoff = (celcius_heat_cutoff - 32) * (5.0 / 9.0)
for room in rooms:
 if room.attributes['active'] != True:
  for vent in room.get_rel('vents'):
    c = vent.attributes['percent-open-reason']
    if get_state(vent) == 100:
        set_state(vent, 0)

 if room.attributes['active'] == True:
  print(room.attributes['name'])
  ctemp = room.attributes['current-temperature-c']
  room_temps[room.attributes['name']] = ctemp
  if direct_vent_control:
    dtemp = direct_setpoints[room.attributes['name']]
    if direct_setpoints_are_f:
      dtemp = (dtemp - 32) * (5.0/9.0)
  else:
    dtemp = room.attributes['set-point-c']

  # Simplied C to F, since flair always repots in C
  if switch_is_f:
    n_delta = (ctemp - dtemp) * (9.0/5.0)
  else:
    n_delta = (ctemp - dtemp)

  if room.attributes['name'] in never_cool and n_delta > 0:
    n_delta = 0
  if room.attributes['name'] in never_heat and n_delta < 0:
    n_delta = 0
  
  # If we're always applying the multiplier, do it before min/max
  # delta, since that is what actually controlls the thermostat
  if room.attributes['name'] in pressure_room_multiplier:
    n_delta *= pressure_room_multiplier[room.attributes['name']]

  if (n_delta*n_delta) > cool_switch_emergency and n_delta > 0:
    print("Forcing cool due to",room.attributes['name'])
    need_force_cool = True
  if (n_delta*n_delta) > heat_switch_emergency and n_delta < 0:
    print("Forcing heat due to",room.attributes['name'])
    need_force_heat = True

  if max_delta < n_delta:
    max_delta = n_delta
  if min_delta > n_delta:
    min_delta = n_delta

  # Apply our room multiplier here.  it goes AFTER max/min delta,
  # because we use room_multiplier to avoid a mode switch, but if the room
  # actually needs cooling, we can just do that... this should prevent the issue where 
  # we run for "a little bit" all night, which reduces life etc etc etc
  if room.attributes['name'] in switch_room_multiplier:
    n_delta *= switch_room_multiplier[room.attributes['name']]

  delta_list.append([n_delta, room])

  print(n_delta)
  if not room.attributes['name'] in no_mode_room:
    # if the user set delta_is_max, only update this if the abs is higher - this way we
    # get the highest room in the system

    # Either way, delta is awlays squared with sign added - this is a least squares situation
    if delta_is_max:
      new_delta = (n_delta*n_delta)*math.copysign(1, n_delta)
      #print(delta,new_delta)
      if math.fabs(new_delta) > math.fabs(delta):
        delta = new_delta
    else:
      delta += (n_delta*n_delta)*math.copysign(1, n_delta)
    rcount += 1

  # Don't do intake room stuff on the intake room :)
  if room.attributes['name'] == intake_room:
    iamintake = True
  else:
    iamintake = False

  for vent in room.get_rel('vents'):
    if vent.attributes['inactive']:
      print("dead vebt :(")
      force_park = True
      #sys.exit(1)
    else:
      actual_vent_count += 1
    c = vent.attributes['percent-open-reason']
    if mode == 'heat' and use_heat_cutoff:
        vent_reading = vent.get_rel("current-reading")
        print ("cutoff:",vent_reading.attributes['duct-temperature-c'],celcius_heat_cutoff)
        if vent_reading.attributes['duct-temperature-c'] > celcius_heat_cutoff:
          print("heat cutoff!",vent_reading.attributes['duct-temperature-c'],celcius_heat_cutoff)
          disable_heat_due_to_overload = True
    print(c)
    print(ctemp,dtemp)
    if 'Manual' in c:
      any_manual = True
      print("Found manual vent in mode",mode,"in state",get_state(vent))
      print("h: at",ctemp*10 - close_offset,"want",dtemp*10)
      print("c: at",ctemp*10 + close_offset,"want",dtemp*10)
      # If vent is _above_ the temp by cool offset, we want to start cooling
      # since we want temp to go _down_ - so open the vent
      if (ctemp*10.0) > (dtemp*10.0 + close_offset) and mode == 'cool' and (not room.attributes['name'] in never_cool):
        print("Vent was closed by us, but should be cooling")
        if get_state(vent) == 0:
          set_state(vent, 100)
      # If vent is _below_ the temp by heat offset, we want to start heating
      # since we want the temp to go _up_ - so open the vent
      if (ctemp*10.0) < (dtemp*10.0 - close_offset) and mode == 'heat' and (not room.attributes['name'] in never_heat):
        print("Vent was closed by us, but should be heating")
        if get_state(vent) == 0:
          set_state(vent, 100)
      # If we have a manual open vent, mock the state
      if get_state(vent) == 100:
        if mode == 'cool':
          c = 'Room is cooling'
        elif mode == 'heat':
          c = 'Room is heating'

    if 'needs cooling' in c or 'is cooling' in c or ('Protect' in c and mode == 'cool'):
      # We close if we should never cool - we trust, for now, that the flair
      # will open it again.  
      if room.attributes['name'] in never_cool:
        print("Vent is cooling, but room",room.attributes['name'],"is in never cool list - force closing!")
        if get_state(vent) == 100:
          set_state(vent, 0)

      print(ctemp,dtemp)
      if int(ctemp*10.0 - 3) > int(dtemp*10.0):
        if (not iamintake) and ctemp > (intake_temp + intake_tollerance) and use_intake_room and (dtemp - ctemp > 0-intake_temp_limit):
          print("Room is more than intake temp, give or take - relying on fan, not even parking")
          #parking = True
          can_use_intake = True
          if inake_vent_temp_bad(room, 'cool',ctemp):
              print("intake over1")
              cooling = True
              can_use_intake = False
        else:
          print("room is cooling")
          can_use_intake = False
          cooling = True
      else:
        print("Skipping cooling because ctemp is actually lower than target",ctemp,"vs",dtemp)
        # if we're closing on target, then we close the vent now.  We undo this if that is no longer met
        # We do this if the vent is _above_ the target by close_offset - i.e. dont we want it to 
        # go down.  If that temp is _higher_, then we want cool
        print(ctemp*10, dtemp*10 - close_offset)
        if close_on_target and (ctemp*10.0) < (dtemp*10.0 - close_offset):
          print("Vent is open, but we hit cool target,",ctemp,"vs",dtemp,", - force closing")
          if get_state(vent) == 100:
            set_state(vent, 0)
        elif ctemp > dtemp and (not iamintake) and ctemp > (intake_temp + intake_tollerance) and use_intake_room and (abs(dtemp - ctemp) < intake_temp_limit):
          print("Room is less than intake temp - relying on fan", ctemp, intake_temp, dtemp - ctemp)
          can_use_intake = True
          if inake_vent_temp_bad(room, 'cool',ctemp):
              print("intake over2")
              parking = True
              cooling = True
              can_use_intake = False
        # just turn off hvac if our return state will be aie
        elif (not iamintake) and ctemp > (intake_temp + intake_tollerance) and use_intake_room and (abs(dtemp - ctemp) < intake_temp_limit):
          print("intake low so disable cool")
          pass
        # Otherwise, we're not cooling, so lets not cool
        #else: 
        #  print("parking1")
        #  parking = True
    if 'needs heating' in c or 'is heating' in c or ('Protect' in c and mode == 'heat'):
      if room.attributes['name'] in never_heat:
        print("Vent is heating, but room",room.attributes['name'],"is in never heat list - force closing!")
        if get_state(vent) == 100:
          set_state(vent, 0)
      print(ctemp*10.0+3,dtemp*10.0)
      if int(ctemp*10.0 + 3) < int(dtemp*10.0):
        if (not iamintake) and ctemp < (intake_temp - 0.5) and use_intake_room and (abs(dtemp - ctemp) < intake_temp_limit):
          print("Room is less than intake temp - relying on fan", ctemp, intake_temp, dtemp - ctemp)
          #parking = True
          can_use_intake = True
          if inake_vent_temp_bad(room, 'heat',ctemp):
              heating = True
              can_use_intake = False
        else:
          print("room is heating")
          can_use_intake = False
          heating = True
      else:
        print("Skipping heating because ctemp is actually higher than target",ctemp,"vs",dtemp)
        # if we're closing on target, then we close the vent now.  We undo this if that is no longer met
        # We do this if the vent is _above_ the target by close_offset - i.e. we dont wabnt it to go _up_
        # If that temp is _lower_, we want heat
        print(ctemp*10 - close_offset, dtemp*10)
        if close_on_target and (ctemp*10.0) > (dtemp*10.0 + close_offset):
          print("Vent is open, but we hit heat target,",ctemp,"vs",dtemp,", - force closing")
          if get_state(vent) == 100:
            set_state(vent, 0)
        elif ctemp < dtemp and (not iamintake) and ctemp < (intake_temp - intake_tollerance) and use_intake_room and (dtemp - ctemp < intake_temp_limit):
          print("Room is less than intake temp - relying on fan", ctemp, intake_temp, dtemp - ctemp)
          #parking = True
          can_use_intake = True
          if inake_vent_temp_bad(room, 'heat',ctemp):
              print("intake over3")
              parking = True
              can_use_intake = False
        elif (not iamintake) and ctemp < (intake_temp - 0.5) and use_intake_room and (dtemp - ctemp < intake_temp_limit):
          pass
        #else:
        #  print("parking2")
        #  parking = True

total_count = 0
open_count = 0
for room in rooms:
  for vent in room.get_rel('vents'):
    total_count += 1
    if get_state(vent) == 100:
      open_count += 1
direct_vent_percent = direct_vent_percent_cool
if heating or mode == 'heat':
  direct_vent_percent = direct_vent_percent_heat
min_open = int(math.ceil((float(total_count) * float(direct_vent_percent)) / 100.0))
print("Total:",total_count,"open:",open_count,"min:",min_open)
while open_count < min_open:
  print("NEED TO FIX BACKPRESSURE!!!!")
  best_candidate = None
  best_diff = 9999
  best_rool = None
  for room in rooms:
    nc = False
    if room.attributes['name'] in never_heat and mode == 'heat':
      nc = True
    if room.attributes['name'] in never_cool and mode == 'cool':
      nc = True
    if room.attributes['name'] in never_bp:
      print("nc:",room.attributes['name'])
      nc = True
    ctemp = room.attributes['current-temperature-c']
    for vent in room.get_rel('vents'):
      if get_state(vent) == 0:
        dtemp = room.attributes['set-point-c']
        diff = abs(ctemp - dtemp)
        if room.attributes['active'] == False:
          diff = diff / 100.0
        if diff < best_diff and not nc:
          best_diff = diff
          best_candidate = vent
          best_room = room
  open_count += 1
  set_state(best_candidate, 100)
  print("Force Open:",best_candidate.attributes['name'],best_diff,best_room.attributes['name'])

# if we've got max cool, close vents on best rooms
if mode == 'cool':
  while open_count > max_cool_vents:
    best_candidate = None
    best_diff = 999
    best_rool = None
    for room in rooms:
        ctemp = room.attributes['current-temperature-c']
        for vent in room.get_rel('vents'):
            if get_state(vent) == 100:
              dtemp = room.attributes['set-point-c']
              # This is not abs, because if it is _colder_, we want it to never open, if it at all makes
              # sense....
              diff = ctemp - dtemp
              if diff < 0:
                  diff = 999 - diff
              if room.attributes['active'] == False:
                diff = 999
              if diff < best_diff:
                best_diff = diff
                best_candidate = vent
                best_room = room
    open_count -= 1
    set_state(best_candidate, 0)
    print("Force close:",best_candidate.attributes['name'],best_diff,best_room.attributes['name'])


if direct_vent_control:
    # We add this here since this only counts non-flair vents
    direct_vent_count += actual_vent_count
    # Sort rooms by temprature delta, reversed if we're in cool mode
    min_open = int(((direct_vent_count)*(100-direct_vent_percent))/100)
    min_open -= (direct_vent_count - actual_vent_count)
    print("min_open =",min_open,"out of",actual_vent_count)
    delta_list = sorted(delta_list)
    if mode == "cool":
      delta_list.reverse()

    open_count = 0
    for d in delta_list:
      room = d[1]
      temp_delta = d[0]
      for vent in room.get_rel('vents'):
        if open_count < min_open or (temp_delta > 0 and mode == 'cool') or (temp_delta < 0 and mode == 'heat'):
          if get_state(vent) != 100:
            print("open vent in",room.attributes['name'],"delta is",temp_delta)
            set_state(vent, 100)
          open_count += 1
        else:
          if get_state(vent) != 0:
            set_state(vent, 100)
            print("close vent in",room.attributes['name'],"delta is",temp_delta)
    sys.exit(1)

if delta_is_average:
  delta /= rcount
if force_park:
  delta = 0
  parking = True
  cooling = False
  heating = False
if disable_heat_due_to_overload:
  heating = False
  parking = False
print("Cooling:",cooling)
print("Heating:",heating)
print("parking",parking)
print("can_use_intake:",can_use_intake)
print("Delta Temp:",delta, min_delta, max_delta)

if os.path.exists("deltat.txt"):
  r = open("deltat.txt", "rb")
  last_delta = pickle.load(r)
  r.close()
else:
  last_delta = []

if os.path.exists("last_switch.pic"):
  r = open("last_switch.pic", "rb")
  last_switch = pickle.load(r)
  r.close()
else:
  last_switch = time.time()


print(last_delta)
last_delta.append(delta)
last_delta = last_delta[-delta_cycles:]
print(last_delta)
f = open("deltat.txt","wb")
pickle.dump(last_delta, f)
f.close()

# if we have to only move a small amount, tell the
# thermostat that instead of the max delta specified
#
# using *5 ibsyead if *10 here to dampen
min_delta *= cool_system_delta
max_delta *= heat_system_delta
if cool_offs > max_delta:
  cool_offs = max_delta 
if heat_offs > 0-min_delta:
  heat_offs = 0-min_delta
#print(cool_offs, heat_offs)

cool_switch_hit = True
heat_switch_hit = True
for d in last_delta:
  if d < cool_switch_threshold:
    cool_switch_hit = False
if d > 0-heat_switch_threshold:
  heat_switch_hit = False
  

# this has to be before tge force ones sibce force overrides this
if (min_heat_time * 69) > (time.time() - last_switch):
  print("OR Ç1")
  cool_switch_hit = False
if (min_cool_time * 69) > (time.time() - last_switch):
  print("OR Ç2")
  heat_switch_hit = False

if need_force_cool and (not need_force_heat):
    cool_switch_hit = True
    heat_switch_hit = False
    print("OR Ç3")
elif need_force_heat and (not need_force_cool):
    cool_switch_hit = False
    heat_switch_hit = True
    print("OR Ç4")
if heat_only:
  cool_switch_hit = False
  heat_switch_hit = True
if cool_only:
  heat_switch_hit = False
  cool_switch_hit = True

print("cs: ",cool_switch_hit)
print("hs: ",heat_switch_hit)

if (heat_complete_timeout * 60) < (time.time() - last_switch):
  print("OR Ç5")
  only_switch_when_heat_complete = False
if (cool_complete_timeout * 60) < (time.time() - last_switch):
  print("OR Ç6")
  only_switch_when_cool_complete = False

# Logic here:
# if both cooling and heating are false, it's okay
# if only_switch_when_complete == False, and mode == heat and only_switch_when_heat_complete == False, it's okay
# if only_switch_when_complete == False, and mode == cool and only_switch_when_cool_complete == False, it's okay
# Otherwise, it's not yet okay
if (cooling == False and heating == False and can_use_intake == False) or (only_switch_when_complete == False and ((mode == 'cool' and only_switch_when_cool_complete == False) or (mode == 'heat' and only_switch_when_heat_complete == False))):
 print('foo')
 if cool_switch_hit and (mode == 'heat' or (force_mode == True and mode != 'cool')):
  print("House is heating, but overall delta is",delta,"above target - switching to cooling")
  structures[0].update(attributes={'structure-heat-cool-mode': 'cool'})
  last_switch = time.time()
  heating = False
  cooling = False
  parking = True
 if heat_switch_hit and (mode == 'cool' or (force_mode == True and mode != 'heat')):
  print("House is cooling, but overall delta is",0-delta,"below target - switching to heating")
  structures[0].update(attributes={'structure-heat-cool-mode': 'heat'})
  last_switch = time.time()
  heating = False
  cooling = False
  parking = True



try:
  pyecobee_db = shelve.open('pyecobee_db', protocol=2)
  ecobee_service = pyecobee_db[ecobee_name]
except KeyError:
  ecobee_service = EcobeeService(thermostat_name = ecobee_name, application_key = ecobee_api_key)
finally:
  pyecobee_db.close()

if ecobee_service.authorization_token is None:
	authorize(ecobee_service)
if ecobee_service.access_token is None:
	request_tokens(ecobee_service)

now_utc = datetime.now(pytz.utc)
if now_utc > ecobee_service.refresh_token_expires_on:
	authorize(ecobee_service)
	request_tokens(ecobee_service)
elif now_utc > ecobee_service.access_token_expires_on:
	token_response = refresh_tokens(ecobee_service)
  

ts = ecobee_service.request_thermostats(Selection(selection_type=SelectionType.REGISTERED.value, selection_match='', include_runtime=True, include_settings=True))
#print(ts.pretty_format())
temp = ts.thermostat_list[0].runtime.actual_temperature
my_fan = FanMode.AUTO
if ts.thermostat_list[0].runtime.desired_fan_mode == 'on':
  my_fan = FanMode.ON
if cooling:
  max_desired = (temp - cool_offs)
  desired = ts.thermostat_list[0].runtime.desired_cool
  if desired !=  max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10), heat_hold_temp=(max_desired / 10) + 6, hold_type=HoldType.INDEFINITE, fan_mode = my_fan)
  else:
    print("Cooling is okay!")
elif heating:
  max_desired = (temp + heat_offs)
  desired = ts.thermostat_list[0].runtime.desired_heat
  if desired != max_desired:
    print("Updating to",max_desired/10,"from",temp)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10)-4, heat_hold_temp=(max_desired / 10), hold_type=HoldType.INDEFINITE, fan_mode = my_fan)
  else:
    print("Heating is okay!")
elif parking:
  if ts.thermostat_list[0].settings.hvac_mode=='cool':
    desired = ts.thermostat_list[0].runtime.desired_cool
    hvac_mode = 'cool'
  else:
    desired = ts.thermostat_list[0].runtime.desired_heat
    hvac_mode = 'heat'
  max_desired = temp
  print(temp,desired)
  if desired != max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10), heat_hold_temp=(max_desired / 10), hold_type=HoldType.INDEFINITE, fan_mode = my_fan)
  else:
    print("parking is okay!")

else:
  # FIXME: select heat/cool based on actual temprature
  if ts.thermostat_list[0].settings.hvac_mode=='cool':
    desired = ts.thermostat_list[0].runtime.desired_cool
    hvac_mode = 'cool'
  else:
    desired = ts.thermostat_list[0].runtime.desired_heat
    hvac_mode = 'heat'
  print(temp,desired)
  print("in disable path temp:",temp,"desired:",desired,hvac_mode)
  # Ensure we're just in range....
  if temp >= (desired - 9) and hvac_mode == 'cool':
      print("Updatring to no cooling")
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+1, heat_hold_temp=(temp / 10) - 1, hold_type=HoldType.INDEFINITE, fan_mode = my_fan)
  
  elif temp <= (desired + 9) and hvac_mode == 'heat':
      print("Updatring to no heating")
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+1, heat_hold_temp=(temp / 10) - 1, hold_type=HoldType.INDEFINITE, fan_mode = my_fan)
  else:
      print("House is okay!")
ts = ecobee_service.request_thermostats(Selection(selection_type=SelectionType.REGISTERED.value, selection_match='', include_runtime=True, include_settings=True))
print("use_intake:",use_intake_room)
print("can_use_intake:",can_use_intake)
print("heat_disabled:",disable_heat_due_to_overload)
print(ts.thermostat_list[0].runtime.desired_cool)
print(ts.thermostat_list[0].runtime.desired_heat)

if use_intake_room and (not disable_heat_due_to_overload):
  if can_use_intake:
    if ts.thermostat_list[0].runtime.desired_fan_mode != 'on':
      print("Turning on ecobee fan...")
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp = ts.thermostat_list[0].runtime.desired_cool / 10.0, heat_hold_temp = ts.thermostat_list[0].runtime.desired_heat / 10.0, fan_mode = FanMode.ON,  hold_type=HoldType.INDEFINITE)
    else:
      print("fan is already on")
  else:
    if ts.thermostat_list[0].runtime.desired_fan_mode != 'auto':
      print("Turning off ecobee fan...")
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp = ts.thermostat_list[0].runtime.desired_cool / 10.0, heat_hold_temp = ts.thermostat_list[0].runtime.desired_heat / 10.0, fan_mode = FanMode.AUTO,  hold_type=HoldType.INDEFINITE)
    else:
      print("fan is already auto")
else:
  print("in non-intake path")
  if ts.thermostat_list[0].runtime.desired_fan_mode != 'auto' and (not disable_heat_due_to_overload):
    print("Resetting ecobee fan!")
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp = ts.thermostat_list[0].runtime.desired_cool / 10.0, heat_hold_temp = ts.thermostat_list[0].runtime.desired_heat / 10.0, fan_mode = FanMode.AUTO,  hold_type=HoldType.INDEFINITE)
  elif ts.thermostat_list[0].runtime.desired_fan_mode != 'on' and disable_heat_due_to_overload:
    print("Turning on ecobee fan during heat overload period...")
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp = ts.thermostat_list[0].runtime.desired_cool / 10.0, heat_hold_temp = ts.thermostat_list[0].runtime.desired_heat / 10.0, fan_mode = FanMode.ON,  hold_type=HoldType.INDEFINITE)

for room in rooms:
  for vent in room.get_rel('vents'):
    for ventname in vent_state.keys():
      if vent.attributes['name'] == ventname:
        v = vent_state[ventname]
        if vent.attributes['percent-open'] != v:
          vent.update(attributes={'percent-open': v})

minutes = (time.time()-last_switch)/60
print("since last switch: ",math.floor(minutes/60),"hours",math.floor(minutes)%60,"minutes")
f = open("last_switch.pic", "wb")
pickle.dump(last_switch, f)
f.close()

# only reset tgese if both intajw is vad ans were not in a vebt lockout
if can_use_intake == False and (bad_vent == False and bad_time == False):
  last_intake = time.time()
  print("reset intake time")

if bad_vent == True:
  last_bad_intake = time.time()

# Any time we're not using the intake, reset this - this ensures that if we only had a problemf or a while,
# we'll reset out of it
if can_use_intake == False:
  f = open("temp_at_intake_start.pic", "wb")
  pickle.dump(room_temps, f)
  f.close()


f = open("last_intake.pic", "wb")
pickle.dump(last_intake, f)
f.close()
f = open("last_bad_intake.pic", "wb")
pickle.dump(last_bad_intake, f)
f.close()

print("intake: ", math.floor(intake_time/60),"minutes",math.floor(intake_time)%60,"seconds")
print("bad_intake: ", math.floor(bad_intake_time/60),"minutes",math.floor(bad_intake_time)%60,"seconds")
