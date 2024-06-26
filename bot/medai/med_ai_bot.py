# encoding:utf-8

import time

import openai
import openai.error
import requests
import datetime
from bot.bot import Bot
from bot.medai.med_ai_session import MedAiSession

from bot.openai.open_ai_image import OpenAIImage
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.token_bucket import TokenBucket
from config import conf, load_config
from utils import redis_servive
import requests
import json
import uuid
from common.mesService import MessageService

# MedAI对话模型API (可用)
class MedAIBot(Bot):
    def __init__(self):
        super().__init__()
        # set the default api_key
        openai.api_key = conf().get("open_ai_api_key")
        if conf().get("open_ai_api_base"):
            openai.api_base = conf().get("open_ai_api_base")
        proxy = conf().get("proxy")
        if proxy:
            openai.proxy = proxy
        if conf().get("rate_limit_chatgpt"):
            self.tb4chatgpt = TokenBucket(conf().get("rate_limit_chatgpt", 20))

        self.sessions = SessionManager(MedAiSession, model=conf().get("model") or "gpt-3.5-turbo")
        self.args = {
            "model": conf().get("model") or "gpt-3.5-turbo",  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在[0,1]之间，越大表示回复越具有不确定性
            # "max_tokens":4096,  # 回复最大的字符数
            "top_p": conf().get("top_p", 1),
            "frequency_penalty": conf().get("frequency_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "presence_penalty": conf().get("presence_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "request_timeout": conf().get("request_timeout", None),  # 请求超时时间，openai接口默认设置为600，对于难问题一般需要较长时间
            "timeout": conf().get("request_timeout", None),  # 重试超时时间，在这个时间内，将会自动重试
        }

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            logger.info("[AIGPT] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            
            query=f"{query} \n注意: 请简短回答并且答案中不要出现 ‘根据文档’ 类似的描述"
                
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
                        # remove system message
            if session.messages[0].get("role") == "system":
                #if app_code or model == "wenxin":
                    session.messages.pop(0)
            logger.debug("[AIGPT] session query={}".format(session.messages))

            api_key = context.get("openai_api_key")
            model = context.get("gpt_model")
            new_args ={} 
            if model:
                new_args = self.args.copy()
                new_args["model"] = model
            # if context.get('stream'):
            #     # reply in stream
            #     return self.reply_text_stream(query, new_query, session_id)

            mapping_code= self._find_group_mapping_code(context)
            if(mapping_code=="smoking"):
                new_args["minimodel"] = "kb"
            else: new_args["minimodel"] = "base_model"
            reply_content = self.reply_text(session,query, api_key, args=new_args)
            
            logger.debug(
                "[AIGPT] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )
            if reply_content["completion_tokens"] == 0 and len(reply_content["content"]) > 0:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
            elif reply_content["completion_tokens"] > 0:
                self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])
                reply = Reply(ReplyType.TEXT, reply_content["content"])
            else:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
                logger.debug("[AIGPT] reply {} used 0 tokens.".format(reply_content))
            return reply

        elif context.type == ContextType.IMAGE_CREATE:
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply
        
    def _find_group_mapping_code(self, context):
        try:
            if context.kwargs.get("isgroup"):
                group_name = context.kwargs.get("msg").from_user_nickname
                #group_mapping = conf().get("group_app_map")
                group_mapping={              
                "专科运营平台需求评审": "default",   
                "AI戒烟专员测试群": "smoking",   
                "文件传输助手": "default",   
                "躺平四人组": "default",   
                "测试gpt": "default",   
                "戒烟问答AI": "smoking",   
                "11月线上戒烟": "smoking",   
                "2023线上戒烟公益活动": "smoking",   
                "朝阳医院戒烟志愿小分队": "smoking",
                "橙心陪诊交流群": "default"
                }
                if group_mapping and group_name:
                    return group_mapping.get(group_name)
        except Exception as e:
            logger.exception(e)
            return None
        
    def reply_text(self, session: MedAiSession, query,api_key=None, args=None, retry_count=0) -> dict:
        """
        call openai's ChatCompletion to get the answer
        :param session: a conversation session
        :param session_id: session id
        :param retry_count: retry count
        :return: {}
        """
        try:
            if conf().get("rate_limit_chatgpt") and not self.tb4chatgpt.get_token():
                raise openai.error.RateLimitError("RateLimitError: rate limit exceeded")
            # if api_key == None, the default openai.api_key will be used
         
            # remove system message
            if session.messages[0].get("role") == "system":
                #if app_code or model == "wenxin":
                    session.messages.pop(0)
            print("model:"+args["minimodel"])
            payload = {
                "action": "assistant",
                "messages": [
                    {
                    "id": str(uuid.uuid4()),
                    "author": {
                        "role": "user",
                        "metadata": {}
                    },
                    "create_time": 0,
                    "update_time": 0,
                    "content": {
                        "content_type": "text",
                        "parts": [
                            query
                        ]
                    },
                    "status": "",
                    "end_turn": False,
                    "weight": 1,
                    "metadata": {},
                    "recipient": "all"
                    }
                ],
                "conversation_id": None,
                "parent_message_id": None,
                "model":  args["minimodel"],
                "timezone_offset_min": 0,
                "suggestions": [],
                "history_and_training_disabled": False,
                "arkose_token": ""
            }

            his=redis_servive.retrieve_object(session.session_id)
            if(his is not None):
                payload["conversation_id"]=his["conversation_id"]
                payload["parent_message_id"]=his["parent_message_id"]

            headers = {
                'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
                'Content-Type': 'application/json',
                "Authorization": "Bearer "+conf().get("open_ai_api_key", ""),
            }

            # response = requests.request("POST", url, headers=headers, data=payload)
            base_url = conf().get("open_ai_api_base", "http://139.196.105.151:59815")
            response = requests.post(url=base_url + "/backend-api/conversation", json=payload, headers=headers,
            timeout=conf().get("request_timeout", 180))
            # print(response.text)
            if response.status_code == 200:
                # execute success
                data=response.text.split("data: ")[-3]
                print(data)
                json_data = json.loads(data)
                messages = json_data['messages']
                reply_content = messages[-1]['content']["parts"][0]
            
                his={
                    "conversation_id":messages[-1]['conversation_id'],
                    "parent_message_id":messages[-1]['message_id']
                }
                redis_servive.store_object(session.session_id,his)
                total_tokens=10
                logger.info(f"[MedAI] reply={reply_content}, total_tokens={total_tokens}")

                mes=MessageService()
                task_data = {
                    'msg_key': str(uuid.uuid4()),
                    'from_account_name': "1",
                    'to_account_name': "2",
                    'create_time': datetime.datetime.now(),
                    'content': 'F001',
                    'question': query,
                    'answer': reply_content,
                    'msg_body': payload,
                }
                mes.create_task(task_data)

                return {
                    "total_tokens": 10,#total_tokens
                    "completion_tokens": 11,
                    "content": reply_content,
                }
            else:
                #response = res.json()
                error = response.text
                # logger.error(f"[LINKAI] chat failed, status_code={response.status_code}, "
                #             f"msg={error.get('message')}, type={error.get('type')}")
                logger.error(error)
                if response.status_code >= 500:
                    # server error, need retry
                    time.sleep(2)
                    logger.warn(f"[LINKAI] do retry, times={retry_count}")
                    #return self.reply_text(session, app_code, retry_count + 1)

                return {
                    "total_tokens": 0,
                    "completion_tokens": 0,
                    "content": "提问太快啦，请休息一下再问我吧"
                }
            
        except Exception as e:
            need_retry = retry_count < 2
            result = {"completion_tokens": 0, "content": "我现在有点累了，等会再来吧"}
            if isinstance(e, openai.error.RateLimitError):
                logger.warn("[AIGPT] RateLimitError: {}".format(e))
                result["content"] = "提问太快啦，请休息一下再问我吧"
                if need_retry:
                    time.sleep(20)
            elif isinstance(e, openai.error.Timeout):
                logger.warn("[AIGPT] Timeout: {}".format(e))
                result["content"] = "我没有收到你的消息"
                if need_retry:
                    time.sleep(5)
            elif isinstance(e, openai.error.APIError):
                logger.warn("[AIGPT] Bad Gateway: {}".format(e))
                result["content"] = "请再问我一次"
                if need_retry:
                    time.sleep(10)
            elif isinstance(e, openai.error.APIConnectionError):
                logger.warn("[AIGPT] APIConnectionError: {}".format(e))
                need_retry = False
                result["content"] = "我连接不到你的网络"
            else:
                logger.exception("[AIGPT] Exception: {}".format(e))
                need_retry = False
                self.sessions.clear_session(session.session_id)

            if need_retry:
                logger.warn("[] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, api_key, args, retry_count + 1)
            else:
                return result

