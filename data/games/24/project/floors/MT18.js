main.floors.MT18=
{
    "floorId": "MT18",
    "title": "第 18 层",
    "name": "第 18 层",
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
        "11,11": {
            "trigger": null,
            "enable": false,
            "noPass": false,
            "displayDamage": false,
            "opacity": 1,
            "filter": {
                "blur": 0,
                "hue": 0,
                "grayscale": 0,
                "invert": false,
                "shadow": 0
            },
            "data": []
        },
        "6,5": [
            {
                "type": "if",
                "condition": "switch:A",
                "true": [
                    "\t[princess]\b[up]请一定要杀死大魔王！"
                ],
                "false": [
                    "\t[勇士,N331]\b[down,hero]公主！你得救了！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]啊，你是来救我的吗？",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[down,hero]是的，我是奉国王的命令来救你的。",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[down,hero]请你快随我出去吧！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]不，我还不想走。",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[down,hero]为什么，这里面到处都是恶魔。",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]正是因为这里面到处都是恶魔，所以才不可以就这样出去，",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]我要看着那个恶魔被杀死！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]英雄的勇士，如果你能够将那个大恶魔杀死，",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]我就和你一起出去！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[down,hero]大恶魔？我已经杀死了一个魔王！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]大恶魔在这座塔的最顶层，你杀死的可能是一个小队长之类的恶魔",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[勇士,N331]\b[down,hero]好，那你等着，等我杀了那个恶魔再来这里找你！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]大恶魔比你刚才杀死的那个厉害多了。",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]而且他还会变身，变身后的魔王他的攻击力",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]和防御力都会提升至少一半以上，你得小心！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    "\t[公主,princess]\b[up,6,5]请一定要杀死大魔王！",
                    {
                        "type": "playSound",
                        "name": "dialogue.mp3"
                    },
                    {
                        "type": "show",
                        "loc": [
                            [
                                11,
                                11
                            ]
                        ],
                        "time": 0
                    },
                    {
                        "type": "setValue",
                        "name": "switch:A",
                        "value": "true"
                    }
                ]
            }
        ]
    },
    "changeFloor": {
        "1,11": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "11,11": {
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
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  1,  1,  1,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1,132,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1,  6,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  1,  1, 83,  1,  1,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  1, 83,  1,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3, 88,  0,  0,  0,  0,  0,  0,  0,  0,  0, 87,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": [
        10,
        11
    ],
    "downFloor": [
        2,
        11
    ],
    "bgm": "area3.mp3",
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}