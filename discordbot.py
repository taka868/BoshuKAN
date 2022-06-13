import discord
import re
from datetime import datetime, timedelta
import pytz
import os
import requests
import json
import traceback

client = discord.Client()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

MENTION_PATTERN = re.compile('<@[0-9]*>')
NUM_PEOPLE_PATTERN = re.compile('@[1-9]')
DATE_PATTERN = re.compile('(0?[1-9]|1[0-2])[/\-月](0?[1-9]|[12][0-9]|3[01])日?')
TIME_PATTERN = re.compile('((0?|1)[0-9]|2[0-3])[:時]([0-5][0-9]分?)?')
LEAGUE_PATTERN = re.compile('リグマ|リーグマッチ')

LEAGUE_INFO_DATETIME = 'date_time'
LEAGUE_INFO_RULE = 'battle_rule'
LEAGUE_INFO_STAGE = 'battle_stage'

LEAGUE_SCHEDULE_URL = 'https://spla2.yuu26.com/league/schedule'

ATTEND_EMOJI = '✋'
ATTEND_CANCEL_EMOJI = '↩'
RECRUITMENT_CANCEL_EMOJI = '🚫'
EMBED_TITLE = f'参加者募集中（{ATTEND_EMOJI}参加 {RECRUITMENT_CANCEL_EMOJI}募集停止）'
RECRUITMENT_STATUS_TITLE = '募集状況'
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
    content_without_mention = re.sub(MENTION_PATTERN, '', content)
    target_num = re.search(NUM_PEOPLE_PATTERN, content_without_mention)
    if target_num is None:
        # 人数が入力されていないメッセージの場合は nop
        print('[DEBUG] Message with no number of people entered.')
        return
    num_of_people = int(target_num.group().replace('@', ''))
    print('[DEBUG] Recruitment begins.')

    # 埋め込みメッセージを作成して送信
    embed_msg = discord.Embed(title=EMBED_TITLE,
                    color=0x000099)
    # 募集状況の作成 メンション数+自分 / 指定数+自分 で人数を設定
    embed_msg = set_recruitment_status_field(embed_msg,
                                             len(message.mentions)+1,
                                             num_of_people+1)

    # 予定開始時刻の作成 時刻と日付を拾って設定
    now = datetime.now(pytz.timezone('Asia/Tokyo'))
    start_time = f'{str(now.hour).zfill(2)}:{str(now.minute).zfill(2)}'
    start_date = f'{now.month}/{now.day}'
    target_time = TIME_PATTERN.search(content)

    # 時刻が入力されている
    if target_time is not None:
        split_time = re.split('[:時分]+', target_time.group())
        if len(split_time) < 2:
            # 分が無い
            split_time.append('0')
        start_time = f'{split_time[0].zfill(2)}:{split_time[1].zfill(2)}'

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
    member_list = [f'<@{message.author.id}>']
    # for member in message.mentions:
    #     member_list.append(f'<@{member.id}>')
    embed_msg.add_field(name=ATTENDEE_LIST_TITLE, value='\n'.join(member_list))

    # リグマ情報の作成
    is_league = re.search(LEAGUE_PATTERN, content)
    if is_league is not None:
        # 設定された時間からリグマ情報を取得
        league_info = fetch_league_schedule(start_datetime)
        if league_info is not None:
            embed_msg.add_field(
                name=f'リグマ {league_info[0][LEAGUE_INFO_DATETIME]}',
                value=f'{league_info[0][LEAGUE_INFO_RULE]}\n{league_info[0][LEAGUE_INFO_STAGE]}')
        if league_info is not None and len(league_info) >= 2:
            embed_msg.add_field(
                name=f'リグマ {league_info[1][LEAGUE_INFO_DATETIME]}',
                value=f'{league_info[1][LEAGUE_INFO_RULE]}\n{league_info[1][LEAGUE_INFO_STAGE]}')
        # TODO: 画像どうしよっかな

    msg = await message.channel.send(embed=embed_msg)

    # リアクションの追加
    await msg.add_reaction(ATTEND_EMOJI)
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
    elif reaction.emoji == RECRUITMENT_CANCEL_EMOJI: # 🚫
        await react_recruitment_cancel(message, user)
    else:
        print('[DEBUG] This emoji is not applicable.')

@client.event
async def on_reaction_remove(reaction, user):
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
        await react_attend_cancel(message, user)
    else:
        print('[DEBUG] This emoji is not applicable.')


async def react_attend(message, user):
    # 参加者一覧の更新
    embed = message.embeds[0]
    idx, attendee = get_attendee_field(embed)
    user_mention = f'<@{user.id}>'
    if user_mention in attendee[0]:
        # 0 は言い出しっぺなので参加表明は無意味
        print('[DEBUG] Message from the recruiter.')
        return
    if user_mention in attendee:
        # 既に登録されている
        print('[DEBUG] Already attending.')
        return

    # リアクションしたユーザーを参加者に追加してメッセージを更新
    attendee.append(user_mention)
    update_value = '\n'.join(attendee)
    embed.set_field_at(idx, name=ATTENDEE_LIST_TITLE, value=update_value)
    # 人数に達したら募集終了
    num_attendee, num_total = get_recruitment_status_field(embed=embed)
    if len(attendee) == num_total:
        # リアクションを削除
        await message.clear_reactions()

        # 募集停止メッセージ
        embed.set_footer(text='※参加者が集まりました')
    set_recruitment_status_field(embed, num_attendee+1, num_total)
    await message.edit(embed=embed)   

    return

async def react_attend_cancel(message, user):
    # 参加者一覧の更新
    embed = message.embeds[0]
    idx, attendee = get_attendee_field(embed)
    user_mention = f'<@{user.id}>'
    if user_mention in attendee[0]:
        # 0 は言い出しっぺなので参加辞退は無意味
        print('[DEBUG] Message from the recruiter.')
        return
    if user_mention not in attendee:
        # 参加表明していないユーザー
        print('[DEBUG] Not attending.')
        return

    # リアクションしたユーザーを参加者から削除してメッセージを更新
    attendee.remove(user_mention)
    update_value = '\n'.join(attendee)
    embed.set_field_at(idx, name=ATTENDEE_LIST_TITLE, value=update_value)

    # 人数を減らす
    num_attendee, num_total = get_recruitment_status_field(embed=embed)
    set_recruitment_status_field(embed, num_attendee-1, num_total)
    await message.edit(embed=embed)   

    return

async def react_recruitment_cancel(message, user):
    # 募集停止
    embed = message.embeds[0]
    idx, attendee = get_attendee_field(embed)
    user_mention = f'<@{user.id}>'
    if attendee[0] != user_mention:
        # 募集を止められるのは言い出しっぺだけ
        print('[DEBUG] Non-recruiter has stopped recruiting.')
        return

    # リアクションを削除
    await message.clear_reactions()

    # 募集停止メッセージ
    embed = message.embeds[0]
    embed.set_footer(text='※募集が停止されました')
    await message.edit(embed=embed)

    return

def get_recruitment_status_field(embed):
    # タイトルが募集状況のものを取得
    for i in range(len(embed.fields)):
        field = embed.fields[i]        
        if field.name == RECRUITMENT_STATUS_TITLE:
            # 最後の数字が総数、その前の数字が集まっている人数になっているはず
            numbers = re.findall(r'\d+', field.value)
            return int(numbers[0]), int(numbers[1])
    # BoshuKAN のメッセージでは参加者一覧がないことはありえない
    return -1, None

def set_recruitment_status_field(embed, num_attendee, num_total):
    for i in range(len(embed.fields)):
        field = embed.fields[i]        
        if field.name == RECRUITMENT_STATUS_TITLE:
            # すでにある場合はフィールドを変更
            embed.set_field_at(i, name=RECRUITMENT_STATUS_TITLE,
                                value=f'{num_attendee} / {num_total}')
            return embed
    embed.add_field(name=RECRUITMENT_STATUS_TITLE,
                        value=f'{num_attendee} / {num_total}')
    return embed

def get_attendee_field(embed):
    # タイトルが参加者一覧のものを取得
    for i in range(len(embed.fields)):
        field = embed.fields[i]        
        if field.name == ATTENDEE_LIST_TITLE:
            # 参加者一覧の取得
            attendee = field.value.split('\n')
            return i, attendee
    # BoshuKAN のメッセージでは参加者一覧がないことはありえない
    return -1, None

def fetch_league_schedule(start_datetime):
    # 面倒なので dict の配列で返す
    league_infos = [{}, {}]

    # 入力は MM/DD hh:mm 形式を前提とする
    split_dt = list(map(int, re.split('[/ :]+', start_datetime)))
    # TODO: 来年の日付をいれることは考慮していない
    start_dt = datetime(datetime.now().year, split_dt[0], split_dt[1], split_dt[2],
                       0, 0, 0, None)
    # 時間を奇数に変換
    if start_dt.hour % 2 == 0:
        start_dt = datetime.combine(
            start_dt.date(), start_dt.time()) + timedelta(hours=-1)
    try:
        response = requests.get(LEAGUE_SCHEDULE_URL)
        schedule_res = json.loads(response.text)
        date_format = '%Y-%m-%dT%H:%M:%S'
        disp_format = '%m/%d %H:%M'
        
        # 指定された時刻に該当するスケジュールを探す
        for i in range(len(schedule_res['result'])):
            schedule = schedule_res['result'][i]
            fetch_dt = datetime.strptime(schedule['start'], date_format)
            # 開始時間に該当するものがあれば設定
            if fetch_dt == start_dt:
                league_infos[0][LEAGUE_INFO_DATETIME] = fetch_dt.strftime(disp_format)
                league_infos[0][LEAGUE_INFO_RULE] = schedule['rule']
                league_infos[0][LEAGUE_INFO_STAGE] = '\n'.join(schedule['maps'])
                if len(schedule_res['result']) > i+2:
                    next = schedule_res['result'][i+1]
                    next_dt = datetime.strptime(next['start'], date_format)
                    league_infos[1][LEAGUE_INFO_DATETIME] = next_dt.strftime(disp_format)
                    league_infos[1][LEAGUE_INFO_RULE] = next['rule']
                    league_infos[1][LEAGUE_INFO_STAGE] = '\n'.join(next['maps'])

    except:
        # API が死んだときはここにくるかも
        traceback.print_exc()
        return None
    return league_infos

client.run(TOKEN)