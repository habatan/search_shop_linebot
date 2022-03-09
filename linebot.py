# -*- choding : utf-8 -*-
# https://ohshima-semi.westus2.cloudapp.azure.com/student2/

from flask import Flask, render_template, redirect, request, jsonify, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, LocationMessage, TextSendMessage, QuickReplyButton, QuickReply,  MessageAction, ImageMessage, LocationAction, TemplateSendMessage, CarouselTemplate, CarouselColumn, PostbackAction, CarouselTemplate, URIAction
)
import json
import requests
from bs4 import BeautifulSoup
import time
import os
import dotenv

dotenv.load_dotenv("_info/.env")

app = Flask(__name__)
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
line_bot_api = LineBotApi(ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
google_api_key = os.getenv("GOOGLE_API_KEY")
google_map_url = "https://www.google.com/maps/search/?api=1"

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'


root_dir = os.getenv("STATIC_IMG_DIR")
sessions = {}
search_words = ["お腹すいた","おなかすいた","お腹空いた","店検索","ご飯たべたい","お店","ご飯"]
selectable_food = ["寿司屋","ラーメン屋","焼肉屋","居酒屋","家で料理する"]
image_urls = [root_dir+"sushi.png",root_dir+"ramen.png",root_dir+"meat.png",root_dir+"bear.png",root_dir+"home.png"]
print(image_urls)


@handler.add(MessageEvent, message=TextMessage)
def reply_message(event):
    global sessions, selectable_food
    
    if not event.source.user_id in sessions.keys():
        sessions[event.source.user_id] = {"flag":False,"food":None,"place":None}
   
    if event.message.text in search_words:
        sessions[event.source.user_id]["flag"]=True
        items = [
            QuickReplyButton(
                action=MessageAction(text=f"{food}",label=f"{food}"),image_url=f"{image_url}"
            ) for food,image_url in zip(selectable_food,image_urls)
        ]
        messages = TextSendMessage(text="どこか食べに行きますか?",quick_reply=QuickReply(items=items))
        line_bot_api.reply_message(event.reply_token, messages=messages)
        
    elif sessions[event.source.user_id]["flag"] and event.message.text in selectable_food[:4]:
        sessions[event.source.user_id]["food"] = event.message.text
        location = [QuickReplyButton(action=LocationAction(label="location"))]
        messages = TextSendMessage(text="現在地教えてください!", quick_reply=QuickReply(items=location))
        line_bot_api.reply_message(event.reply_token, messages=messages)
        
    elif sessions[event.source.user_id]["flag"] and event.message.text == "家で料理する":
        # 記事取得
        cookpad_url = "https://cookpad.com"
        response = requests.get(cookpad_url)
        article = ""
        soup1 = BeautifulSoup(response.content)
        # date class = idea_date
        date = soup1.find("div",class_="idea_date").text.strip("\n")+"日"
        # topic class = idea_article_title
        topic = soup1.find("div",class_="idea_article_title").text.replace("\n","")
        # nextURL
        header_recipe = soup1.find("a",class_="idea_article")["href"]
        article += "{}のおすすめレシピは : {}\n\n".format(date,topic)

        # レシピ詳細
        content = requests.get(cookpad_url+header_recipe).content
        soup2 = BeautifulSoup(content)
        menus = soup2.find_all("a",class_="recipe recipe_small")
        for i,menu in enumerate(menus):
            target_url = menu["href"]
            title = menu.find("div",class_="recipe_title").text
            ingredients = menu.find("div",class_="ingredients").text.replace("\n","")
            recipe = "その{} [{}]\n".format(i+1,title.strip("\n"))+ingredients + "\nURL : {}\n\n".format(cookpad_url+target_url)
            article += recipe
        message = TextSendMessage(text=article)
        line_bot_api.reply_message(event.reply_token, message)
        
    else:
        help_message = "おなかすいたなぁ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_message))
        
        
#  位置情報を扱う(webhookイベントオブジェクトで検索)       
@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    global sessions, google_api_key, google_map_url
    
    # useridを取得できているか確認
    print("useridの取得 : ",event.source.user_id)
    print("sessionの状態 : ",sessions)
    print("messageの種類 : ",event.message.type)
    
    if sessions[event.source.user_id]["flag"] and sessions[event.source.user_id]["food"]:
        latitude = event.message.latitude
        longitude = event.message.longitude
        # thumnailImage
        data = find_place_by_geoinfo(
            latitude=latitude,longitude=longitude,keyword=sessions[event.source.user_id]["food"]
        )
        columns = []
        for i in range(len(data["results"][:10])):
            # columnsは10までしか加えることができない
            try:
                photo_reference = data["results"][i]["photos"][0]["photo_reference"]
                # map_url_content = data["results"][i]["photos"][0]["html_attributions"]
                # map_url = BeautifulSoup(map_url_content[0]).find("a")["href"]
                image_url = get_photoURL(photo_reference)
                # shop_name and shop_rating
                shop_name = data["results"][i]["name"]
                like_num = data["results"][i]["rating"]
                place_id = data["results"][i]["place_id"]
                user_ratings_total = data["results"][i]['user_ratings_total']
                latitude = data["results"][i]['geometry']['location']["lat"]
                longitude = data["results"][i]['geometry']['location']["lng"]
                
                map_url = google_map_url+f"&query={latitude}%2C{longitude}&quary_place_id={place_id}"
                print(map_url)                
                carousel = make_carousel(
                    thumbnail_image_url=image_url, shop_name=shop_name, like=like_num, user_ratings_total=user_ratings_total, map_url=map_url
                )
                columns.append(carousel)
            except:
                continue
        if len(columns)>= 1:
            message = TextSendMessage(text="近くにこんなお店があるみたい")
            line_bot_api.reply_message(event.reply_token, message)
            carousel_template_message = TemplateSendMessage(
                alt_text='Carousel template',
                template=CarouselTemplate(columns=columns)
            )
            # 2段でメッセージの送信
            time.sleep(0.4)
            line_bot_api.push_message(event.source.user_id, carousel_template_message)
        else:
            message = TextSendMessage(text="1km以内に候補が見つかりませんでした")
            line_bot_api.reply_message(event.reply_token, messages=mssage)
        
# placeAPIから得たphoto_referenceをもちいて画像URLを作成
def get_photoURL(photo_reference):
    global google_api_key
    # jsonから抜き出したデータで写真を取得
    root_url = "https://maps.googleapis.com/maps/api/place/photo?"
    # option
    maxwidth = "400"
    photo_url = root_url+"maxwidth="+maxwidth+"&photo_reference="+photo_reference+"&key="+google_api_key
    return photo_url

# carousel_message作成関数
def make_carousel(thumbnail_image_url,shop_name,like,map_url,user_ratings_total):
    column = CarouselColumn(
            thumbnail_image_url=thumbnail_image_url,
            title=shop_name,
            text=f"いいね👍 :{like}\n評価数 :{user_ratings_total}",
            actions=[URIAction(label='mapで表示',uri=map_url)]
            )
    return column

# restauranto情報を入手する関数
def find_place_by_geoinfo(latitude, longitude, keyword)->str:
    global google_api_key
    # https://developers.google.com/maps/documentation/places/web-service/search-nearby
    place_api = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?keyword={keyword}&types=food?language=ja&location={latitude},{longitude}&radius=1000&key="

    response = requests.get(place_api+google_api_key)
    soup = BeautifulSoup(response.content)
    data = json.loads(soup.text)
    return data

if __name__ == "__main__":
    app.run(port=19808,debug=True)


