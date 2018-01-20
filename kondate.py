from errbot import BotPlugin, botcmd, webhook
from bottle import response
from errbot.backends.base import Card, Identifier, Message, RoomOccupant
from typing import Any, Mapping, BinaryIO, List, Sequence, Tuple
import json
import re
import os

class Kondate(BotPlugin):
    """Decide today's menu"""

    COLORS = {
        'red': '#FF0000',
        'green': '#008000',
        'yellow': '#FFA500',
        'blue': '#0000FF',
        'white': '#FFFFFF',
        'cyan': '#00FFFF'
    }

    MEAL = ['breakfast', 'lunch', 'dinner']

    def make_cancel_msg(self):
        """make json message for canceling"""
        return {
            "name": "cancel",
            "text": "cancel",
            "type": "button",
            "style": "danger",
            "confirm": {
                "title": "Are you sure?",
                "text": "Wouldn't you eat?",
                "ok_text": "Yes",
                "dismiss_text": "No"
            }
        }

    def make_ephemeral_msg(self, text):
        """make json message that is only visible for sender"""
        return json.dumps({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": text
        })

    @botcmd
    def kondate(self, msg, args):
        """plan today's breakfast, lunch, and dinner"""
        actions = [{
            "name": "breakfast",
            "text": "select a morning menu...",
            "type": "select",
            "data_source": "external"
        },
                   self.make_cancel_msg()]
        body = 'What do you eat for breakfast?'
        callback_id = 'breakfast'
        self.send_slack_attachment_action(
            body=body,
            callback_id=callback_id,
            actions=actions,
            color='#3AA3E3',
            in_reply_to=msg)

    def send_slack_attachment_action(self,
                                     body: str = '',
                                     to: Identifier = None,
                                     in_reply_to: Message = None,
                                     summary: str = None,
                                     title: str = '',
                                     link: str = None,
                                     image: str = None,
                                     thumbnail: str = None,
                                     color: str = 'green',
                                     fields: Tuple[Tuple[str, str], ...] = (),
                                     callback_id: str = None,
                                     fallback: str = None,
                                     actions=[]) -> None:
        """
        send attachment message.
        this code is customized from errbot.botplugin and errbot.backends.slack
        """

        frm = in_reply_to.to if in_reply_to else self.bot_identifier
        if to is None:
            if in_reply_to is None:
                raise ValueError('Either to or in_reply_to needs to be set.')
            to = in_reply_to.frm

        if isinstance(to, RoomOccupant):
            to = to.room
        to_humanreadable, to_channel_id = self._bot._prepare_message(
            Card(body, frm, to, in_reply_to, summary, title, link, image,
                 thumbnail, color, fields))
        attachment = {}
        if actions:
            attachment['actions'] = actions
        if callback_id:
            attachment['callback_id'] = callback_id

        if summary:
            attachment['pretext'] = summary
        if title:
            attachment['title'] = title
        if link:
            attachment['title_link'] = link
        if image:
            attachment['image_url'] = image
        if thumbnail:
            attachment['thumb_url'] = thumbnail
        if fallback:
            attachment['fallback'] = fallback
        attachment['text'] = body

        if color:
            attachment['color'] = self.COLORS[color] if color in self.COLORS else color

        if fields:
            attachment['fields'] = [{
                'title': key,
                'value': value,
                'short': True
            } for key, value in fields]

        data = {
            'text': ' ',
            'channel': to_channel_id,
            'attachments': json.dumps([attachment]),
            'link_names': '1',
            'as_user': 'true'
        }
        try:
            self.log.debug('Sending data:\n%s', data)
            self._bot.api_call('chat.postMessage', data=data)
        except Exception as e:
            self.log.exception(
                "An exception occurred while trying to send a card to %s.[%s]"
                % (to_humanreadable, data))

    @webhook(form_param='payload')
    def slack_request(self, payload):
        if 'SLACK_VERIFICATION_TOKEN' not in os.environ:
            self.log.info('SLACK_VERIFICATION_TOKEN needs to be set.')
            response.set_header("Content-type", "application/json")
            return self.make_ephemeral_msg("`SLACK_VERIFICATION_TOKEN` needs to be set.")
        slack_token = os.environ['SLACK_VERIFICATION_TOKEN']
        if payload['token'] != slack_token:
            self.log.info('SLACK_VERIFICATION_TOKEN is invalid.')
            response.set_header("Content-type", "application/json")
            return self.make_ephemeral_msg("`SLACK_VERIFICATION_TOKEN` is invalid.")

        self.log.debug("accepted payload:{}".format(payload))
        action_name = payload['actions'][0]['name']
        user = payload['user']['name']
        message = payload['original_message']
        attachment_size = len(message['attachments'])
        if action_name in self.MEAL:
            # rewrite existed attachment.
            selected_value = payload['actions'][0]['selected_options'][0][
                'value']
            message['attachments'][attachment_size - 1] = {
                "fields": [{
                    "title":
                    action_name,
                    "value":
                    "@{0} eats {1}!".format(user, selected_value),
                    "short":
                    False
                }],
                "actions": [],
                "color":
                '#3AA3E3'
            }
            # define next meal and append attachment.
            if self.MEAL.index(action_name) != len(self.MEAL) - 1:
                next_meal = self.MEAL[self.MEAL.index(action_name) + 1]
                action = {
                    "name": next_meal,
                    "text": "select a {} menu...".format(next_meal),
                    "type": "select",
                    "data_source": "external"
                }
                message['attachments'].append({
                    "text":
                    "What do you eat for {}?".format(next_meal),
                    "actions": [action, self.make_cancel_msg()],
                    "callback_id":
                    next_meal
                })
            self.log.debug(message)
        elif action_name == 'cancel':
            # when canceling, rewrite existed attachment.
            message['attachments'][attachment_size - 1] = {
                "fields": [{
                    "title": "@{} canceled".format(user),
                    "short": False
                }],
                "actions": [],
                "color":
                '#3AA3E3'
            }

        response_message = json.dumps(message)
        self.log.debug("response message:{}".format(response_message))
        response.set_header("Content-type", "application/json")
        return response_message

    @webhook(form_param='payload')
    def external_options(self, payload):
        self.log.debug("accepted payload:{}".format(payload))
        message_morning_list = {
            "options": [{
                "text": "toast",
                "value": "toast"
            }, {
                "text": "rice",
                "value": "rice"
            }]
        }
        message_lunch_list = {
            "options": [{
                "text": "spaghetti",
                "value": "spaghetti"
            }, {
                "text": "rice bowl",
                "value": "rice bowl"
            }, {
                "text": "ramen",
                "value": "ramen"
            }]
        }
        message_dinner_list = {
            "options": [{
                "text": "sushi",
                "value": "sushi"
            }, {
                "text": "tempura",
                "value": "tempura"
            }, {
                "text": "sukiyaki",
                "value": "sukiyaki"
            }]
        }

        if payload['callback_id'] == 'breakfast':
            message = message_morning_list
        elif payload['callback_id'] == 'lunch':
            message = message_lunch_list
        elif payload['callback_id'] == 'dinner':
            message = message_dinner_list
        response_message = json.dumps(message)
        response.set_header("Content-type", "application/json")
        self.log.debug('Sending data(option):\n%s', response_message)
        return response_message
