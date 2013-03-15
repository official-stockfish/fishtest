import os, json

with open(os.path.expanduser('~/fishtest.users'), 'r') as f:
  USERS = json.load(f)

GROUPS = {'glinscott': ['group:admins'],
          'mcostalba': ['group:admins'],
          'lbraesch': ['group:admins'],}

def groupfinder(userid, request):
  if userid in USERS:
    return GROUPS.get(userid, [])
