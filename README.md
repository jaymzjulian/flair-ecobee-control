About
------

DISCLAIMER: If you break your HVAC with this, I am not responsible.  If this worries you, I strongly recommend not using this.  While it works for me, this is absolutely hack level - in particular, this is why it is not provided with API keys and such.  If you're not able to obtain your own API keys, you probably shouldn't be using this...

This is a tool for managing the combination of flair and ecobee when you want to have significantly differnet tempratures per room, and fine grained control of that - out of the box, it will still use the flair code for vent management, so that part will be safe.  THere is an option to control the vents directly, but this still very much work in progress.

The reason for this existing is that, due to medical issues, we have one household member who needs the temprature at 75F, and one who needs the temprature to never go above around 67F.  

I run this every 2 minutes from cron to manage my household vents, and it's been working well for me for about 6 months.  The configuration in demo-settings.py is the actual configuration I use in my house.

Getting Started
----------------

This relies on the `pyecobee` and `flair_api` python modules.  To use these, you'll need two things:

a) An API key for ecobee - this can be gotten from ecobee.com by signing up for a developer account
b) An API key for flair - when I did this last time, you had to file a support request, but this may have changed!

Both of these need to go into secrets.py - see demo-secrets.py as an example

Once you've configured settings.py appropriately (tempate from demo-settings.py), you should be able to run at the CLI for the first time.  When you do this, it will prompt you to go to a generated URL to confirm your API key usage (both the flair and ecobee APIs are optimized around hosted webapps, and assume that the webapp will redirect the user to this URL - hence the requirement for hard coded API keys as well....).  Once you've done this, the auth will be stored in pyecobee_db.dat, and you'll be good to go.  

I recommend running this in the foreground for a little to check it does what you want - in screen I was originally running:

```
screen -m 'while true; do python3 ./flair-ecobeepy ; sleep 120 ; done'
```

But of course, eventually you almost certainly want to run it from cron or systemd

Tips
----
When starting out tuning your settings, do monitor the ecobee system stats to ensure that you're not constantly cycling your HVAC - that's the major reason for the temprature pressure options in the settings.  The issue we had, was the warm room was heating the vents themselves - this heat would dissapate, but originally the system was aggressive enough that it was turning on the AC and, well, a bad time was had by all.  Reducing the pressure setting for the super cold room worked this out.
