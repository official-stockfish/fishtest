from celery import Celery

rabbit = 'aqmp://task:tasks@54.235.120.254//'
celery = Celery('tasks', broker=rabbit, backend=rabbit)
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
