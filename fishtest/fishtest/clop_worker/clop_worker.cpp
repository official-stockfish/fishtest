#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <assert.h>

#include "zmq.hpp"

int main(int argc, char** argv)
{
  zmq::context_t context(1);
  zmq::socket_t socket(context, ZMQ_REP);
  socket.bind("tcp://*:5555");
  while (true) {
    zmq::message_t request;
    socket.recv(&request);

    sleep(1);

    zmq::message_t reply(5);
    memcpy(reply.data(), "world", 5);
    socket.send(reply);
  }
  return 0;
}
