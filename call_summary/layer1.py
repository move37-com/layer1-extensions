import redis.asyncio as redis
import asyncio
import json
import uuid
from fnmatch import fnmatch

class MessageCenter:
    queue = {}
    r = redis.Redis(host='localhost', port=6381, decode_responses=True)
    handlers = {}

    def __init__(self, loop, extension_id):
        self.loop = loop
        self.extension_id = extension_id
        self.pubsub = self.r.pubsub()

    def run(self):
        print("Listening for Layer1 events...")
        self.loop.run_until_complete(self.listen_for_messages())

    def subscribe(self, channel, handler):
        self.handlers[channel] = handler

    async def send_message(self, msg):
        responseID = str(uuid.uuid4())
        msg["responseID"] = responseID
        msg["extensionID"] = self.extension_id
        msg["origin"] = "extension"

        resp_future = asyncio.Future()
        self.queue[responseID] = resp_future
        await self.r.publish("messages", json.dumps(msg))
        result = await resp_future
        return result
    
    async def listen_for_messages(self):
        await self.pubsub.subscribe(*self.handlers.keys(), 'messages')
        while True:
            try:
                msg = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg:
                    self.triage_msg(msg['channel'], json.loads(msg['data']))
            except asyncio.CancelledError:
                raise
            except:
                print("Layer1 connection closed. Retrying...")
                await asyncio.sleep(1)

    def triage_msg(self, channel, msg):
        if channel == 'messages':
            # Only handle incoming messages directed at our extension
            # Also ignore any messages broadcast by ourself (origin)
            if msg['origin'] == 'app' and msg['extensionID'] == self.extension_id:
                self._handle_response(msg['responseID'], msg['data'])
        else:
            for chan, handler in self.handlers.items():
                if fnmatch(channel, chan):
                    try:
                        self.loop.create_task(handler(channel, msg['event'], msg['data']))
                    except Exception as e:
                        print("Event handler error raised: ", e)
                    break

    # Handles incoming responses on the 'messages' channel
    def _handle_response(self, responseID, msg):
        if self.queue[responseID]:
            self.queue[responseID].set_result(msg)
            del self.queue[responseID]
        else:
            print("Warning: no response handler found for responseID: ", responseID)
