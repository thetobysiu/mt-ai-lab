main.floors.MT2=
{
    "floorId": "MT2",
    "title": "第 2 层",
    "name": "第 2 层",
    "width": 13,
    "height": 13,
    "canFlyTo": true,
    "canUseQuickShop": true,
    "cannotViewMap": false,
    "images": [],
    "ratio": 1,
    "defaultGround": "ground",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {
        "8,11": [
            "\t[勇士,N331]\b[hero]您已经得救了！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[老人,man]\b[up]哦，我的孩子，真是太感谢你了！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[老人,man]\b[up]这个地方又脏又坏，我真的是快呆不下去了。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[勇士,N331]\b[hero]快走吧，我还得救走被关在这里的公主。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[老人,man]\b[up]哦，你是来救公主的，为了表示对你的感谢，",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[老人,man]\b[up]这个东西就送给你吧，这还是我年青的时候用过的。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[老人,man]\b[up]拿着它去解救公主吧！",
            {
                "type": "setValue",
                "name": "item:sword2",
                "operator": "+=",
                "value": "1"
            },
            {
                "type": "playSound",
                "name": "dialogue.mp3",
                "stop": true
            },
            {
                "type": "playSound",
                "name": "unlockCtrl.mp3"
            },
            {
                "type": "hide",
                "time": 0
            }
        ],
        "10,11": [
            "\t[勇士,N331]\b[hero]您已经得救了！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[商人,trader]\b[up]哦，是嘛！真是太感谢你了！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[商人,trader]\b[up]我是个商人，不知为什么被抓到这里来了。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[勇士,N331]\b[hero]快走吧，现在您已经自由了。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[商人,trader]\b[up]哦，对对对，我已经自由了。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[商人,trader]\b[up]那这个东西就给你吧，本来我是准备卖钱的。",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[商人,trader]\b[up]相信它对你一定很有帮助！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            {
                "type": "playSound",
                "name": "unlockCtrl.mp3"
            },
            {
                "type": "setValue",
                "name": "item:shield2",
                "operator": "+=",
                "value": "1"
            },
            {
                "type": "hide",
                "time": 0
            }
        ]
    },
    "changeFloor": {
        "1,1": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "1,11": {
            "floorId": ":next",
            "stair": "downFloor"
        }
    },
    "afterBattle": {},
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3, 88,  1,  0,227,  0,  1, 27, 28, 21, 23,  1,  3],
    [  3,  0,  1, 28,  1, 32,  1, 27, 28, 21, 22,  1,  3],
    [  3,  0,  1, 21,  1, 21,  1, 27, 28, 21,226,  1,  3],
    [  3,  0,  1, 21,  1, 21,  1,  1,  1,  1, 81,  1,  3],
    [  3,  0,  1,  0,  1,  0,  0,  0, 81,  0,  0,  1,  3],
    [  3,  0,  1, 81,  1,  1, 81,  1,  1, 81,  1,  1,  3],
    [  3,  0, 85,  0,  0,  0,  0,  1,  0,226,  0,  1,  3],
    [  3,  0,  1, 81,  1,  1, 82,  1,  6,  1,  6,  1,  3],
    [  3,  0,  1, 21,  1, 32, 31,  1,  0,  1,  0,  1,  3],
    [  3,  0,  1, 21,  1, 32, 31,  1,  0,  1,  0,  1,  3],
    [  3, 87,  1, 27,  1, 32, 31,  1,121,  1,122,  1,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "bgm": "area1.mp3",
    "upFloor": [
        1,
        10
    ],
    "downFloor": [
        1,
        2
    ],
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}