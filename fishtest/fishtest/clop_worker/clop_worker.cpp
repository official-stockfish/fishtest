#include <zmq.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <assert.h>

int main (void)
{
  //  Socket to talk to clients
  void *context = zmq_ctx_new();
  void *responder = zmq_socket(context, ZMQ_REP);
  int rc = zmq_bind(responder, "tcp://*:5555");
  while (1) {
    char buffer[1000];
    zmq_recv(responder, buffer, 1000, 0);
    printf("Received %s\n", buffer);
    zmq_send(responder, "World", 5, 0);
    sleep(1);          //  Do some 'work'
  }
  return 0;
}
