from pyramid.security import Allow, Everyone

class RootFactory(object):
  __acl__ = [ (Allow, Everyone, 'view'),
              (Allow, 'group:admins', 'modify_db') ]
  def __init__(self, request):
    pass

