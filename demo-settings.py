# For all ecobee settings, they're multiplied by 10 for degrees - so cool_offs of 20 means "use 2 degrees"
# What the subtract from the current temp when forcing the ecobee to cool
cool_offs = 20
# What the add to the current temp when forcing the ecobee to cool
heat_offs = 10

# Delta multiplier for heat/cool adjustments to the ecobee - 5 is literally half the number of degrees, 10 is exactly the number
# 5 works well for me - 10 overshoots and causes heat/cool cycles.
cool_system_delta = 5
heat_system_delta = 5

# Switch to cool when the squared temprature difference is above this 
# Since this is all rooms added together, we _probably_ should average ir or something...
# The meaning of this and heat_switch_thresholf are affected by the 
# settings below (switch_is_f, delta_is_average, delta_is_max) and excludes rooms in
# the list no_mode_room
cool_switch_threshold = 4.0
# Switch to cool if we _ever_ excceed this, ignoring the 
# heat switch
cool_switch_emergency = 8.0
# Switch to heat when the squared temprature difference is below this 
# Since this is all rooms added together, we _probably_ should average ir or something...
heat_switch_threshold = 5.0
# Swithc to heat if we ever exceed this, ignoring the cool switch
heat_switch_emergency = 128.0

# How many cycles must be be out of range for before we switch types
# JJ fixme: this needs to be in minutes, not cycles....
delta_cycles = 1

# Set this to change the heat switch to f - default is C
switch_is_f = True

# Set this to make the delta an _average_ of all rooms
delta_is_average = False

# Set this to make the delta the _MAX_ room differnec,e rather than all rooms summed
delta_is_max = True

# These rooms won't be involved in switching temp - do this if you have 
# rooms where you don't care.  See also "switch_room_multipliuer" below for a
# more nuanced version of this!  
#no_mode_room = ["Kman", "Front"]
no_mode_room = []

# If you have a room specifically from which air intake happens, you 
# can put it here - if the current temp is _less_ than the intake room, instead of cool
# it will just set to park and try and use the fan...
use_intake_room = False
intake_room = "Kitchen / living room"

# set this to obly switch mode when the nothing is heathibg/coolibg
# This can be useful if you have one room that only gets occupied at 
# certain parts of the day, and you want to ensure that when it _does_ get
# occupied, it continues to cool/heat until it reaches target temprature
#
# It can also avoid short cycling.  It will, however, lead to less accurate tempratures.
only_switch_when_complete = False

# Bypass flair's automatic vent control, and control them manually?
# Note that this will bypass all of the safetys in the flair system, and you
# absolutely should not do this unless you _seriously_ know what you are doing!!
# In particular, closing too many vents _CAN DAMAGE YOUR HVAC SYSTEM_
direct_vent_control = False
# The number of vents in your house for direct control, which are NOT flair vents
direct_vent_count = 0
# The maximum percentage of vents to close at any given time - be very careful
# with this setting, as again closing too many vents _CAN DAMAGE YOUR HVAC SYSTEM_
direct_vent_percent = 30

# Switch room multiplier _only_ affects whether
# the thermostat switches from hot to cold - but it will use the 
# Same level of pressure to push air to the room as if it was at full
# consideration.  In my case, I use this for a room where the person 
# inside it wants their room way colder than the rest of the house, but can deal
# with a larger temprature range if it "eventually" gets back there - this
# avoids his room turning off the heating to the rest of the house!
#
# The reason you would avoid this, is because you can't generally just do "one" room,
# and so backpressure prevcention will ensure that, even if you're cooling/heating just
# one room, some of that will go into other rooms - so maybe you want to
# entirely back off while this is happening, to avoid affecting other rooms.  
# In that case, pressure_room_multiplier is a better option, but of course
# beware of short cycling!
switch_room_multiplier = { 'Kman': 0.7 }

# Pressure room multiplier affects _both_ - use this when you
# want to also not blow as much air into a room.  This is used to
# compensate for a laggy thermostat gnerally (in my case, the ecobee
# unit itself is slow to update, but the flair puck and ecobee sensors are
# fast, so I put the room with that in here)
#
# Note that this can cause "short cycling", where it will run the air
# for short amounts of time to maintain the temprature.  Depending on 
# your unit, this can be a bad thing...
pressure_room_multiplier = {
        'Kitchen / living room': 0.7,
        'Front': 0.6 }

# Force mode override, even if someohe marks it auto
force_mode = True
