from __future__ import absolute_import
import os

from celery import Celery

ip = os.getenv('FISHTEST_IP')
if ip == None:
  ip = '54.235.120.254' 

rabbit = 'amqp://tasks:tasks@' + ip + '/fishtest'
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
