import redis.asyncio as redis
import asyncio
import json
import uuid

class MessageCenter:
    queue = {}
    r = redis.Redis(host='localhost', port=6381, decode_responses=True)

    def __init__(self, loop, extension_id):
        self.loop = loop
        self.extension_id = extension_id

    def run(self):
        pubsub = self.r.pubsub()
        self.loop.run_until_complete(self.listen(pubsub))
    
    async def send_message(self, msg):
        responseID = str(uuid.uuid4())
        msg["responseID"] = responseID
        msg["extensionID"] = self.extension_id
        msg["origin"] = "extension"
        print("Sending message: ", msg)

        resp_future = asyncio.Future()
        self.queue[responseID] = resp_future
        await self.r.publish("messages", json.dumps(msg))
        result = await resp_future
        return result

    async def listen(self, pubsub):
        await pubsub.subscribe('events', 'messages')
        while True:
            try:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg:
                    self.triage_msg(msg['channel'], json.loads(msg['data']))
            except asyncio.CancelledError:
                raise
            except:
                print("Connection closed")
                await asyncio.sleep(1)

    def triage_msg(self, channel, msg):
        match channel:
            case 'events':
                if self.event_handler:
                    try:
                        self.loop.create_task(self.event_handler(msg['event'], msg['data']))
                    except Exception as e:
                        print("Event handler error raised: ", e)
            case 'messages':
                # Only handle incoming messages directed at our extension
                # Also ignore any messages broadcast by ourself (origin)
                if msg['origin'] == 'app' and msg['extensionID'] == self.extension_id:
                    self.handle_response(msg['responseID'], msg['data'])
        
    # Handles incoming responses on the 'messages' channel
    def handle_response(self, responseID, msg):
        if self.queue[responseID]:
            self.queue[responseID].set_result(msg)
            del self.queue[responseID]
        else:
            print("Warning: no response handler found for responseID: ", responseID)



# Create a MessageCenter instance
extension_id = str(uuid.uuid4())
loop = asyncio.get_event_loop()
message_center = MessageCenter(loop, extension_id)

async def handleCallDidEnd(msg):
    print('Call ended: ', msg['callID'])
    script_msg = {
        "event": "layerScript.run",
        "data": {
            "scriptName": "Call Summary",
            # "scriptInput": str(msg['callID'])
            "scriptInput": "1693939913"
        }
    }
    print("Sending summary request")
    summary_msg = await message_center.send_message(script_msg)
    print("Got summary result")
    summary = summary_msg['summary']
    view_msg = {
        "event": "view.renderHTML",
        "data": {
            "html": summary
        }
    }
    print("Sending view render request")
    status = await message_center.send_message(view_msg)
    print("Render status: ", status)

async def event_handler(event, msg):
    print("Got global event: ", event)
    match event:
        case 'callRecordings.callDidEnd':
            await handleCallDidEnd(msg)


# Assign global event handler and start the message center
message_center.event_handler = event_handler
message_center.run()