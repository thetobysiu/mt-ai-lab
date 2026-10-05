main.floors.MT16=
{
    "floorId": "MT16",
    "title": "第 16 层",
    "name": "第 16 层",
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
        "6,5": {
            "trigger": null,
            "enable": true,
            "noPass": true,
            "displayDamage": false,
            "opacity": 1,
            "filter": {
                "blur": 0,
                "hue": 0,
                "grayscale": 0,
                "invert": false,
                "shadow": 0
            },
            "data": [
                "\t[勇士,N331]\b[hero]……",
                {
                    "type": "playSound",
                    "name": "dialogue.mp3"
                },
                "\t[红衣魔王,redKing]\b[down,6,6]停止吧，愚蠢的人类！",
                {
                    "type": "playSound",
                    "name": "dialogue.mp3"
                },
                "\t[勇士,N331]\b[hero]该停止的是你！魔王。快说，公主关在哪里？",
                {
                    "type": "playSound",
                    "name": "dialogue.mp3"
                },
                "\t[红衣魔王,redKing]\b[down,6,6]等你打赢我再说吧！",
                {
                    "type": "playSound",
                    "name": "dialogue.mp3"
                },
                {
                    "type": "hide",
                    "time": 0
                }
            ]
        },
        "5,5": [
            {
                "type": "if",
                "condition": "(core.getBlockCls(5,5)=='npcs')",
                "true": [
                    "\t[老人,man]\b[down]年青人，你终于来了！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[hero]您怎么了？",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[老人,man]\b[down]我已经快封不住它了，请你将这个东西交给彩蝶仙子，",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[老人,man]\b[down]她会告诉你这是什么东西，有什么用的！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[老人,man]\b[down]快去吧，再迟就来不及了！",
                    {
                        "type": "hide",
                        "time": 0
                    },
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
                        "name": "flag:16",
                        "value": "1"
                    },
                    {
                        "type": "autoText",
                        "text": "\t[得到神秘宝物！]\b[down,hero] ",
                        "time": 500
                    }
                ]
            }
        ]
    },
    "changeFloor": {
        "7,1": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "6,8": {
            "floorId": ":next",
            "stair": "downFloor"
        }
    },
    "afterBattle": {
        "6,6": [
            {
                "type": "function",
                "function": "function(){\ncore.setEnemy('darkKnight', 'hp', 1600);\ncore.setEnemy('darkKnight', 'atk', 1306);\ncore.setEnemy('darkKnight', 'def', 1200);\ncore.setEnemy('darkKnight', 'money', 117);\ncore.setEnemy('darkKnight', 'exp', 100);\n\ncore.setEnemy('ghostSkeleton', 'hp', 3333);\ncore.setEnemy('ghostSkeleton', 'atk', 1200);\ncore.setEnemy('ghostSkeleton', 'def', 1133);\ncore.setEnemy('ghostSkeleton', 'money', 112);\ncore.setEnemy('ghostSkeleton', 'exp', 100);\n\ncore.setEnemy('blackMagician', 'hp', 2000);\ncore.setEnemy('blackMagician', 'atk', 1106);\ncore.setEnemy('blackMagician', 'def', 973);\ncore.setEnemy('blackMagician', 'money', 106);\ncore.setEnemy('blackMagician', 'exp', 93);\n\ncore.setEnemy('redKing', 'hp', 20000);\ncore.setEnemy('redKing', 'atk', 1333);\ncore.setEnemy('redKing', 'def', 1333);\ncore.setEnemy('redKing', 'money', 133);\ncore.setEnemy('redKing', 'exp', 133);\n}"
            }
        ]
    },
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3,  4,  4,  4,  4,  4,  0, 88,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  0,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  0,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  1, 83,  1,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,121,  0,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1,245,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1,  0,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1, 87,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  1,  1,  1,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": [
        6,
        7
    ],
    "downFloor": [
        6,
        1
    ],
    "bgm": "area3.mp3",
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}