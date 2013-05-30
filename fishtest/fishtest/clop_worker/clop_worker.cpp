#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <assert.h>

#include "zmq.hpp"

int main(int argc, char** argv)
{
  zmq::context_t context(1);
  zmq::socket_t socket(context, ZMQ_REQ);
  socket.connect("tcp://127.0.0.1:5000");
  while (true) {
    zmq::message_t message(5);
    snprintf(static_cast<char*>(message.data()), 5, "%s", argv[1]);
    socket.send(message);

    zmq::message_t request;
    socket.recv(&request);
    printf("Got %s\n", static_cast<char*>(request.data()));

    sleep(1);
  }
  return 0;
}
