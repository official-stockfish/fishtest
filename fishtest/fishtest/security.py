import os, ujson

with open(os.path.expanduser('~/fishtest.users'), 'r') as f:
  USERS = ujson.load(f)

GROUPS = {'glinscott': ['group:admins'],
          'mcostalba': ['group:admins']}

def groupfinder(userid, request):
  if userid in USERS:
    return GROUPS.get(userid, [])
