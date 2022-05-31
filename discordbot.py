import discord
import re
import datetime
import pytz
import os
import asyncio

client = discord.Client()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

NUM_PEOPLE_PATTERN = re.compile('@[1-9]')
DATE_PATTERN = re.compile('(0?[1-9]|1[0-2])[/\-月](0?[1-9]|[12][0-9]|3[01])日?')
TIME_PATTERN = re.compile('((0?|1)[0-9]|2[0-3])[:時][0-5][0-9]分?')

ATTEND_EMOJI = '✋'
ATTEND_CANCEL_EMOJI = '↩'
RECRUITMENT_CANCEL_EMOJI = '🚫'

EMBED_TITLE = f'参加者募集中（{ATTEND_EMOJI}参加 {ATTEND_CANCEL_EMOJI}参加取消 {RECRUITMENT_CANCEL_EMOJI}募集停止）'
ATTENDEE_LIST_TITLE = '参加者一覧'

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_message(message):
    print(f'on_message content=\'{message.content}\'')
    # message から文字列を取得
    content = message.content

    # メッセージから人数の取得
    target_num = re.search(NUM_PEOPLE_PATTERN, content)
    if target_num is None:
        # 人数が入力されていないメッセージの場合は nop
        print('[DEBUG] Message with no number of people entered.')
        return
    num_of_people = int(target_num.group().replace('@', ''))

    # 埋め込みメッセージを作成して送信
    embed_msg = discord.Embed(title=EMBED_TITLE,
                    color=0x000099)
    # 募集状況の作成 メンション数+自分で人数を設定
    embed_msg.add_field(name='募集状況',
                        value=f'{len(message.mentions)+1} / {num_of_people}')

    # 予定開始時刻の作成 時刻と日付を拾って設定
    now = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
    start_time = f'{now.hour}:{now.minute}'
    start_date = f'{now.month}/{now.day}'
    target_time = TIME_PATTERN.search(content)
    # 時刻が入力されている
    if target_time is not None:
        print(target_time.group())
        time_str = target_time.group()
        if '時' in time_str:
            if '分' not in time_str:
                # TODO: 正規表現的にここはこないかも。"21時"とかでも 21:00 で発動させたい
                time_str.join('00')
            start_time = time_str.replace('時', ':').replace('分', '')
        else:
            start_time = time_str

        target_date = DATE_PATTERN.search(content)
        # 日付が入力されている
        if target_date is not None:
            print(target_date.group())
            date_str = target_date.group()
            if '月' in date_str:
                start_date = target_date.replace('月', '/').replace('日', '')
            else:
                start_date = date_str
    start_datetime = f'{start_date} {start_time}'
    embed_msg.add_field(name='予定開始時刻', value=start_datetime)

    # 参加者一覧の作成
    member_list = [f'@{message.author.name}']
    for member in message.mentions:
        member_list.append(f'@{member.name}')
    print(member_list)
    embed_msg.add_field(name=ATTENDEE_LIST_TITLE, value='\n'.join(member_list))

    msg = await message.channel.send(embed=embed_msg)

    # リアクションの追加
    await msg.add_reaction(ATTEND_EMOJI)
    await msg.add_reaction(ATTEND_CANCEL_EMOJI)
    await msg.add_reaction(RECRUITMENT_CANCEL_EMOJI)

@client.event
async def on_reaction_add(reaction, user):
    print(f'on_reaction_add content=\'{reaction.emoji}\'')
    if user.bot:
        # bot 発信のリアクションの場合は nop
        print('[DEBUG] Reactions sent by the bot.')
        return

    # そもそも BoshuKAN 発信のメッセージじゃなかったら
    message = reaction.message
    if message.author.name != 'BoshuKAN':
        print('[DEBUG] This message is not applicable.')
        return

    # 各リアクションごとの処理を実行
    if reaction.emoji == ATTEND_EMOJI: # ✋
        await react_attend(message, user)
    elif reaction.emoji == ATTEND_CANCEL_EMOJI: # ↩
        await react_attend_cancel(message, user)
    elif reaction.emoji == RECRUITMENT_CANCEL_EMOJI: # 🚫
        await react_recruitment_cancel(message, user)

async def react_attend(message, user):
    # 参加者一覧の更新
    embed = message.embeds[0]
    idx, attendee = get_attendee_field(embed)
    if attendee[0] == user.name:
        # 0 は言い出しっぺなので参加表明は無意味
        print('[DEBUG] Message from the recruiter.')
        return
    if user.name in attendee:
        # 既に登録されている
        print('[DEBUG] Already attending.')
        return

    # リアクションしたユーザーを参加者に追加してメッセージを更新
    attendee.append(f'@{user.name}')
    update_value = '\n'.join(attendee)
    embed.set_field_at(idx, name=ATTENDEE_LIST_TITLE, value=update_value)
    message.edit(embed=embed)
    return

async def react_attend_cancel(message, user):
    # 参加者一覧の更新
    embed = message.embeds[0]
    idx, attendee = get_attendee_field(embed)
    if attendee[0] == user.name:
        # 0 は言い出しっぺなので参加辞退は無意味
        print('[DEBUG] Message from the recruiter.')
        return
    if user.name not in attendee:
        # 参加表明していないユーザー
        print('[DEBUG] Not attending.')
        return

    # リアクションしたユーザーを参加者から削除してメッセージを更新
    attendee.append(f'@{user.name}')
    update_value = '\n'.join(attendee)
    embed.set_field_at(idx, name=ATTENDEE_LIST_TITLE, value=update_value)
    message.edit(embed=embed)
    return

async def react_recruitment_cancel(message, user):

    # リアクションを削除
    await message.clear_reactions()
    return

def get_attendee_field(embed):
    for i in range(len(embed.fields)):
        field = embed.fields[i]        
        if field.name == ATTENDEE_LIST_TITLE:
            # 参加者一覧の取得
            attendee = field.value.split('\n')
            return i, attendee
    # BoshuKAN のメッセージでは参加者一覧がないことはありえない
    return -1, None

client.run(TOKEN)