from flair_api import make_client
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

def persist_to_shelf(file_name, ecobee_service):
    pyecobee_db = shelve.open(file_name, protocol=2)
    pyecobee_db[ecobee_service.thermostat_name] = ecobee_service
    pyecobee_db.close()


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



client = make_client(client_id, client_secret, 'https://api.flair.co/')

# retrieve a list of structures available to this account
structures = client.get('structures')
mode = structures[0].attributes['structure-heat-cool-mode']
print("Mode is",mode)

rooms = client.get('rooms')

cooling = False
heating = False
parking = False
delta = 0.0
intake_temp = 999
# If using an intake room, find that first since earlier rooms
# may need it
if use_intake_room:
  for room in rooms:
    if room.attributes['active'] == True:
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
for room in rooms:
 if room.attributes['active'] == True:
  print(room.attributes['name'])
  ctemp = room.attributes['current-temperature-c']
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
    print(c)
    print(ctemp,dtemp)
    if 'Manual' in c:
      any_manual = True
      print("Found manual vent in mode",mode,"in state",vent.attributes['percent-open'])
      print("h: at",ctemp*10 - close_offset,"want",dtemp*10)
      print("c: at",ctemp*10 + close_offset,"want",dtemp*10)
      # If vent is _above_ the temp by cool offset, we want to start cooling
      # since we want temp to go _down_ - so open the vent
      if (ctemp*10.0) > (dtemp*10.0 + close_offset) and mode == 'cool':
        print("Vent was closed by us, but should be cooling")
        if vent.attributes['percent-open'] == 0:
          vent.update(attributes={'percent-open': 100, 'percent-open-reason': 'Room is cooling'})
      # If vent is _below_ the temp by heat offset, we want to start heating
      # since we want the temp to go _up_ - so open the vent
      if (ctemp*10.0) < (dtemp*10.0 - close_offset) and mode == 'heat':
        print("Vent was closed by us, but should be heating")
        if vent.attributes['percent-open'] == 0:
          vent.update(attributes={'percent-open': 100, 'percent-open-reason': 'Room is heating'})
      # If we have a manual open vent, mock the state
      if vent.attributes['percent-open'] == 100:
        if mode == 'cool':
          c = 'Room is cooling'
        elif mode == 'heat':
          c = 'Room is heating'

    if 'needs cooling' in c or 'is cooling' in c or ('Protect' in c and mode == 'cool'):
      # We close if we should never cool - we trust, for now, that the flair
      # will open it again.  
      if room.attributes['name'] in never_cool:
        print("Vent is cooling, but room is in never cool list - force closing!")
        if vent.attributes['percent-open'] == 100:
          vent.update(attributes={'percent-open': 0, 'percent-open-reason': 'mode was cool, but vent is in never_cool list'})

      print(ctemp,dtemp)
      if int(ctemp*10.0 - 3) > int(dtemp*10.0):
        if (not iamintake) and ctemp > (intake_temp + 0.25) and use_intake_room and (dtemp - ctemp > -2.0):
          print("Room is more than intake temp, give or take - parking instead and relying on fan")
          parking = True
        else:
          print("room is cooling")
          cooling = True
      else:
        print("Skipping cooling because ctemp is actually lower than target",ctemp,"vs",dtemp)
        # if we're closing on target, then we close the vent now.  We undo this if that is no longer met
        # We do this if the vent is _above_ the target by close_offset - i.e. dont we want it to 
        # go down.  If that temp is _higher_, then we want cool
        print(ctemp*10, dtemp*10 - close_offset)
        if close_on_target and (ctemp*10.0) < (dtemp*10.0 - close_offset):
          print("Vent is open, but we hit cool target,",ctemp,"vs",dtemp,", - force closing")
          if vent.attributes['percent-open'] == 100:
            vent.update(attributes={'percent-open': 0, 'percent-open-reason': 'mode was cool, but hit target'})
        parking = True
    if 'needs heating' in c or 'is heating' in c or ('Protect' in c and mode == 'heat'):
      if room.attributes['name'] in never_heat:
        print("Vent is cooling, but room is in never cool list - force closing!")
        if vent.attributes['percent-open'] == 100:
          vent.update(attributes={'percent-open': 0, 'percent-open-reason': 'mode was cool, but vent is in never_cool list'})
      print(ctemp*10.0+3,dtemp*10.0)
      if int(ctemp*10.0 + 3) < int(dtemp*10.0):
        if (not iamintake) and ctemp < (intake_temp - 0.5) and use_intake_room and (dtemp - ctemp < 2.0):
          print("Room is less than intake temp - parking instead and relying on fan", ctemp, intake_temp, dtemp - ctemp)
          parking = True
        else:
          print("room is heating")
          heating = True
      else:
        print("Skipping heating because ctemp is actually higher than target",ctemp,"vs",dtemp)
        # if we're closing on target, then we close the vent now.  We undo this if that is no longer met
        # We do this if the vent is _above_ the target by close_offset - i.e. we dont wabnt it to go _up_
        # If that temp is _lower_, we want heat
        print(ctemp*10 - close_offset, dtemp*10)
        if close_on_target and (ctemp*10.0) > (dtemp*10.0 + close_offset):
          print("Vent is open, but we hit heat target,",ctemp,"vs",dtemp,", - force closing")
          if vent.attributes['percent-open'] == 100:
            vent.update(attributes={'percent-open': 0, 'percent-open-reason': 'mode was heat, but hit target'})
        parking = True

total_count = 0
open_count = 0
for room in rooms:
  for vent in room.get_rel('vents'):
    total_count += 1
    if vent.attributes['percent-open'] == 100:
      open_count += 1
min_open = int(math.ceil((float(total_count) * float(direct_vent_percent)) / 100.0))
print("Total:",total_count,"open:",open_count,"min:",min_open)
while any_manual and open_count < min_open:
  print("NEED TO FIX BACKPRESSURE!!!!")
  best_candidate = None
  best_diff = 9999
  best_rool = None
  for room in rooms:
    nc = False
    if room.attributes['name'] in never_bp and mode == 'cool':
      print("nc:",room.attributes['name'])
      nc = True
    ctemp = room.attributes['current-temperature-c']
    for vent in room.get_rel('vents'):
      if vent.attributes['percent-open'] == 0:
        dtemp = room.attributes['set-point-c']
        diff = abs(ctemp - dtemp)
        if room.attributes['active'] == False:
          diff = 0
        if diff < best_diff and not nc:
          best_diff = diff
          best_candidate = vent
          best_room = room
  open_count += 1
  best_candidate.update(attributes={'percent-open': 100, 'percent-open-reason': 'back pressure protect by JJ!'})
  print("Force Open:",best_candidate.attributes['name'],best_diff,best_room.attributes['name'])



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
          if vent.attributes['percent-open'] != 100:
            print("open vent in",room.attributes['name'],"delta is",temp_delta)
            vent.update(attributes={'percent-open': 100, 'percent-open-reason': 'opening for '+mode+' due to delta '+str(temp_delta)})
          open_count += 1
        else:
          if vent.attributes['percent-open'] != 0:
            vent.update(attributes={'percent-open': 0, 'percent-open-reason': 'closing for '+mode+' due to delta '+str(temp_delta)})
            print("close vent in",room.attributes['name'],"delta is",temp_delta)
    sys.exit(1)

if delta_is_average:
  delta /= rcount
if force_park:
  delta = 0
  parking = True
  cooling = False
  heating = False
print("Cooling:",cooling)
print("Heating:",heating)
print("parking",parking)
print("Delta Temp:",delta, min_delta, max_delta)

if os.path.exists("deltat.txt"):
  r = open("deltat.txt", "rb")
  last_delta = pickle.load(r)
  r.close()
else:
  last_delta = []

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

if need_force_cool and (not need_force_heat):
    cool_switch_hit = True
    heat_switch_hit = False
elif need_force_heat and (not need_force_cool):
    cool_switch_hit = False
    heat_switch_hit = True

print("cs: ",cool_switch_hit)
print("hs: ",heat_switch_hit)

if (cooling == False and heating == False) or only_switch_when_complete == False:
 if cool_switch_hit and (mode == 'heat' or (force_mode == True and mode != 'cool')):
  print("House is heating, but overall delta is",delta,"above target - switching to cooling")
  structures[0].update(attributes={'structure-heat-cool-mode': 'cool'})
  heating = False
  cooling = False
  parking = True
 if heat_switch_hit and (mode == 'cool' or (force_mode == True and mode != 'heat')):
  print("House is cooling, but overall delta is",0-delta,"below target - switching to heating")
  structures[0].update(attributes={'structure-heat-cool-mode': 'heat'})
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
if cooling:
  max_desired = (temp - cool_offs)
  desired = ts.thermostat_list[0].runtime.desired_cool
  if desired !=  max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10), heat_hold_temp=(max_desired / 10) + 6, hold_type=HoldType.INDEFINITE)
  else:
    print("Cooling is okay!")
elif heating:
  max_desired = (temp + heat_offs)
  desired = ts.thermostat_list[0].runtime.desired_heat
  if desired != max_desired:
    print("Updating to",max_desired/10,"from",temp)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10)-4, heat_hold_temp=(max_desired / 10), hold_type=HoldType.INDEFINITE)
  else:
    print("Heating is okay!")
elif parking:
  if ts.thermostat_list[0].settings.hvac_mode=='cool':
    desired = ts.thermostat_list[0].runtime.desired_cool
    hvac_mode = 'cool'
  else:
    desired = ts.thermostat_list[0].runtime.desired_heat
    hvac_mode = 'head'
  max_desired = temp
  print(temp,desired)
  if desired != max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10), heat_hold_temp=(max_desired / 10), hold_type=HoldType.INDEFINITE)
  else:
    print("parking is okay!")

else:
  # FIXME: select heat/cool based on actual temprature
  if ts.thermostat_list[0].settings.hvac_mode=='cool':
    desired = ts.thermostat_list[0].runtime.desired_cool
    hvac_mode = 'cool'
  else:
    desired = ts.thermostat_list[0].runtime.desired_heat
    hvac_mode = 'head'
  print(temp,desired)
  # Ensure we're just in range....
  if temp >= desired and hvac_mode == 'cool':
      print("Updatring to no cooling/heating")
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+1, heat_hold_temp=(temp / 10) - 1, hold_type=HoldType.INDEFINITE)
  
  elif temp <= desired and hvac_mode == 'heat':
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+1, heat_hold_temp=(temp / 10) - 1, hold_type=HoldType.INDEFINITE)
  else:
      print("House is okay!")
