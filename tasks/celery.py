from __future__ import absolute_import
import os

from celery import Celery

# RabbitMQ server is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
fishtest_host = os.getenv('FISHTEST_HOST')
if len(fishtest_host) == 0:
  fishtest_host = 'localhost'
rabbit = 'amqp://tasks:tasks@%s/fishtest' % (fishtest_host)

celery = Celery('tasks', broker=rabbit, backend=rabbit, include=['tasks.games'])
celery.add_defaults({
  'CELERY_ROUTES': {
    'tasks.games.run_games': {'queue': 'games'}
  },
  'CELERYD_PREFETCH_MULTIPLIER': 1,
  'CELERY_ACKS_LATE': True,
  'CELERY_SEND_TASK_SENT_EVENT': True,
})

if __name__ == '__main__':
  celery.start()
