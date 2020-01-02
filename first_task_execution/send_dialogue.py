import sys
import json

sys.path.append('.')
sys.path.append('..')

from tasks.dialogue import send_dialogue_task_from_weiboid

if __name__ == '__main__':
    filename = 'weibo_id.json'
    with open(filename) as f:
        weibo_id = json.load(f)
    send_dialogue_task_from_weiboid(weibo_id)
