import layer1
import asyncio
import json
import uuid
import objectpath

# Create a MessageCenter instance
extension_id = str(uuid.uuid4())
loop = asyncio.get_event_loop()
message_center = layer1.MessageCenter(loop, extension_id)

poll_task = None

async def start_recording(pid):
    print("START RECORDING")

async def stop_recording(pid):
    print("STOP RECORDING")

# Electron apps need to have AX enabled before any window elements become visible
async def enable_electron_ax(pid):
    msg = {
        'event': 'ax.setAttributeValue',
        'data': {
            'pid': pid,
            'attribute': 'AXManualAccessibility',
            'boolValue': True
        }
    }
    await message_center.send_message(msg)

async def find_huddle_controls(pid):
    print("Find controls")
    msg = {
        'event': 'ax.getProcessTree',
        'data': {
            'pid': pid
        }
    }
    tree_resp = await message_center.send_message(msg)
    windows = tree_resp['windows']
    for window in windows:
        window_tree = objectpath.Tree(window)
        huddle_controls = window_tree.execute("$..children[@.description is 'Huddle controls']")
        for entry in huddle_controls:
            if 'uuid' in entry:
                print("Found huddle controls")
                return entry['uuid']

async def find_gallery(uuid):
    print("Find gallery")
    msg = {
        'event': 'ax.getNodeTree',
        'data': {
            'uuid': uuid
        }
    }
    tree_resp = await message_center.send_message(msg)
    huddle_controls = tree_resp['node']
    controls_tree = objectpath.Tree(huddle_controls)
    gallery = controls_tree.execute("$..children[@.description is 'Gallery']")
    for entry in gallery:
        if 'uuid' in entry:
            print("Found gallery")
            return True
    print("Gallery not found")
    return False

async def poll_slack_ax(pid):
    huddle_controls = None
    on_call = False

    await enable_electron_ax(pid)
    
    while True:
        try:
            if huddle_controls == None:
                # Find top-level huddle controls in full AX tree
                huddle_controls = await find_huddle_controls(pid)
            if huddle_controls:
                # Check for Gallery within huddle controls element
                is_call = await find_gallery(huddle_controls)
                print("On call: ", is_call)
                if is_call and not on_call:
                    # Huddle was just started; start recording now
                    await start_recording(pid)
                elif on_call and not is_call:
                    # Huddle just ended; stop recording now
                    await stop_recording(pid)
                on_call = is_call
        except:
            # Exception was raised; likely the AX element became invalid
            # Force a full AX tree refresh
            huddle_controls = None

        # Wait before polling again
        await asyncio.sleep(3)

async def check_slack_running():
    def is_slack(app):
        return 'bundleID' in app and app['bundleID'] == 'com.tinyspeck.slackmacgap'
    msg = {
        "event": "system.getRunningApps"
    }
    resp = await message_center.send_message(msg)
    apps = resp['runningApps']
    slack_proc = next(filter(lambda app: is_slack(app), apps), None)
    if slack_proc:
        # Slack is running; start polling AX now
        global poll_task
        poll_task = loop.create_task(poll_slack_ax(slack_proc['pid']))
        
async def sys_handler(channel, event, msg):
     match event:
        case 'applicationDidLaunch':
            if 'bundleID' in msg and msg['bundleID'] == 'com.tinyspeck.slackmacgap':
                # Slack launched; poll huddle status
                global poll_task
                pid = msg['pid']
                poll_task = loop.create_task(poll_slack_ax(pid))
        case 'applicationDidTerminate':
            if 'bundleID' in msg and msg['bundleID'] == 'com.tinyspeck.slackmacgap':
                # Slack no longer running; cancel polling
                poll_task.cancel()

# Check once at startup if Slack is already running
# loop.create_task(check_slack_running())
loop.create_task(check_slack_running())

# Register event handler and start the message center
message_center.subscribe('system', sys_handler)
message_center.run() # Will run forever