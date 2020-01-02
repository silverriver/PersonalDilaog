import json, re

from bs4 import BeautifulSoup

from logger import parser
from db.models import WeiboDialoggue
from decorators import parse_decorator
from .comment import get_html_cont


@parse_decorator([])
def get_comment_id(html, wb_id):
    """
    获取评论列表
    :param html:
    :param wb_id:
    :return:
    """
    cont = get_html_cont(html)
    if not cont:
        return list()

    soup = BeautifulSoup(cont, 'lxml')
    comment_ids = list()
    comments = soup.find(attrs={'node-type': 'comment_list'}).find_all(attrs={'class': 'list_li S_line1 clearfix'})

    for comment in comments:
        try:
            comment_cont = comment.find(attrs={'class': 'WB_text'}).text.strip()
            if '回复@' in comment_cont:
                comment_ids.append(comment['comment_id'])
        except Exception as e:
            parser.error('解析评论失败，具体信息是{}'.format(e))

    return comment_ids


def get_dialogue(html, wb_id, cid):
    """
    获取对话列表
    :param html:
    :param wb_id:
    :return:
    """
    cont = get_html_cont(html)
    soup = BeautifulSoup(cont, 'lxml')
    dialogue_list = []
    dialogues = soup.find_all(attrs={'class': 'WB_text'})
    comments = soup.find_all(attrs={'class': 'line S_line1'})
    times = soup.find_all('div', class_='time_s')
    if len(dialogues) < 2:
        return None, None
    weibo_dialogue = WeiboDialoggue()
    uids = []
    try:
        for idx, dialogue in enumerate(dialogues):
            post_time = times[idx].text.strip()
            user_id = dialogue.find('a').get('usercard')[3:]
            uids.append(user_id)
            comment = comments[idx * 2 + 1].a.get('action-data')
            pattern = re.compile(r'cid=(.+?)&')
            search = pattern.search(comment)
            if search:
                comment_id = search.group(1)
            dialogue_list.append(
                {'uid': user_id, 'cid': comment_id, 'text': dialogue.text.strip(), 'post_time': post_time})
        weibo_dialogue.weibo_id = wb_id
        weibo_dialogue.dialogue_id = cid
        weibo_dialogue.dialogue_cont = json.dumps(dialogue_list)
        weibo_dialogue.dialogue_rounds = len(dialogues)
    except Exception as e:
        parser.error('解析对话失败，具体信息是{}'.format(e))
        return None, None
    return weibo_dialogue, uids
