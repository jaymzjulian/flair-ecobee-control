from flair_api import make_client
import shelve
from datetime import datetime
import pytz
from six.moves import input
from pyecobee import *


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

client = make_client(client_id, client_secret, 'https://api.flair.co/')

# retrieve a list of structures available to this account
structures = client.get('structures')

rooms = client.get('rooms')

cooling = False
heating = False
for room in rooms:
  print(room.attributes['name'])
  for vent in room.get_rel('vents'):
    c = vent.attributes['percent-open-reason']
    ctemp = room.attributes['current-temperature-c']
    dtemp = room.attributes['set-point-c']
    if 'is cooling' in c:
      if int(ctemp*10.0) > int(dtemp*10.0):
        print("room is cooling")
        cooling = True
      else:
        print("Skipping cooling because ctemp is actually lower than target",ctemp,"vs",dtemp)
    if 'is heating' in c:
      if int(ctemp*10.0) > int(dtemp*10.0):
        print("room is cooling")
        heating = True
      else:
        print("Skipping cooling because ctemp is actually higher than target",ctemp,"vs",dtemp)
print("Cooling:",cooling)
print("Heating:",heating)



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
  max_desired = (temp - 20)
  desired = ts.thermostat_list[0].runtime.desired_cool
  if desired > max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10), heat_hold_temp=(max_desired / 10) + 6, hold_type=HoldType.INDEFINITE)
  else:
    print("Cooling is okay!")
elif heating:
  max_desired = (temp + 20)
  desired = ts.thermostat_list[0].runtime.desired_heat
  if desired < max_desired:
    print("Updating to",max_desired/10)
    update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(max_desired / 10)-4, heat_hold_temp=(max_desired / 10), hold_type=HoldType.INDEFINITE)
  else:
    print("Heating is okay!")
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
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+2, heat_hold_temp=(temp / 10) - 2, hold_type=HoldType.INDEFINITE)
  
  elif temp <= desired and hvac_mode == 'heat':
      update_thermostat_response = ecobee_service.set_hold(cool_hold_temp=(temp / 10)+2, heat_hold_temp=(temp / 10) - 2, hold_type=HoldType.INDEFINITE)
  else:
      print("House is okay!")
