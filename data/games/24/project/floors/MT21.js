main.floors.MT21=
{
    "floorId": "MT21",
    "title": "第 21 层",
    "name": "第 21 层",
    "width": 13,
    "height": 13,
    "canFlyTo": false,
    "canUseQuickShop": false,
    "cannotViewMap": false,
    "images": [],
    "ratio": 1,
    "defaultGround": "ground",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {},
    "changeFloor": {
        "6,8": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "6,1": {
            "floorId": ":next",
            "stair": "downFloor"
        }
    },
    "afterBattle": {
        "6,2": [
            "\t[冥灵魔王,vampire]啊……\n怎么可能，我怎么可能会被你打败呢！",
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            "\t[冥灵魔王,vampire]不，不要这样…………",
            {
                "type": "function",
                "function": "function(){\ncore.setEnemy('redKing', 'hp', 30000);\ncore.setEnemy('redKing', 'atk', 2666);\ncore.setEnemy('redKing', 'def', 2666);\ncore.setEnemy('redKing', 'money', 166);\ncore.setEnemy('redKing', 'exp', 166);\n\ncore.setEnemy('darkKnight', 'hp', 2400);\ncore.setEnemy('darkKnight', 'atk', 2612);\ncore.setEnemy('darkKnight', 'def', 2400);\ncore.setEnemy('darkKnight', 'money', 146);\ncore.setEnemy('darkKnight', 'exp', 125);\n\ncore.setEnemy('ghostSkeleton', 'hp', 4999);\ncore.setEnemy('ghostSkeleton', 'atk', 2400);\ncore.setEnemy('ghostSkeleton', 'def', 2266);\ncore.setEnemy('ghostSkeleton', 'money', 140);\ncore.setEnemy('ghostSkeleton', 'exp', 125);\n\ncore.setEnemy('blackMagician', 'hp', 3000);\ncore.setEnemy('blackMagician', 'atk', 2212);\ncore.setEnemy('blackMagician', 'def', 1946);\ncore.setEnemy('blackMagician', 'money', 132);\ncore.setEnemy('blackMagician', 'exp', 116);\n\ncore.setEnemy('vampire', 'hp', 60000);\ncore.setEnemy('vampire', 'atk', 3400);\ncore.setEnemy('vampire', 'def', 3000);\ncore.setEnemy('vampire', 'money', 390);\ncore.setEnemy('vampire', 'exp', 343);\n}"
            },
            {
                "type": "playSound",
                "name": "dialogue.mp3"
            },
            {
                "type": "if",
                "condition": "(flag:22==0)",
                "true": [
                    {
                        "type": "playSound",
                        "name": "door.mp3"
                    },
                    {
                        "type": "setCurtain",
                        "color": [
                            0,
                            0,
                            0,
                            1
                        ],
                        "time": 0
                    },
                    {
                        "type": "confirm",
                        "text": "看剧情？",
                        "yes": [
                            {
                                "type": "scrollText",
                                "text": "大魔头被杀死了,公主也被救出了塔,蝶仙的精力也恢复了\n当勇士和公主一起走出塔来的时候，\n国王也带着军队来到了岛外。一切都是那么地平常。\n回国后，国王为勇士和公主举行了隆重而且盛大的婚礼，\n并且宣布由勇士继承国王的位置。\n从此以后，勇士和公主就幸福地生活在一起了",
                                "time": 10000,
                                "lineHeight": 5
                            }
                        ],
                        "no": []
                    },
                    {
                        "type": "if",
                        "condition": "flag:战斗动画",
                        "true": [
                            {
                                "type": "win",
                                "reason": "回味经典（不计榜）",
                                "norank": 1
                            }
                        ],
                        "false": [
                            {
                                "type": "while",
                                "condition": "true",
                                "data": [
                                    {
                                        "type": "choices",
                                        "text": "\t[king]选择要提交的榜单！",
                                        "choices": [
                                            {
                                                "text": "生命值",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"生命\""
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "攻击值（最高）",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"最高攻击\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:atk",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "防御值（最高）",
                                                "condition": "false",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"最高防御\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:def",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "攻防和（最高）",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"最高攻防和\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:atk + status:def",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "等级",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"等级\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:lv",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "金币数量",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"金币\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:money",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "经验值",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"经验\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "status:exp",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "商店购买次数（最高）",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:t",
                                                        "value": "flag:shop1_hp_buy+flag:shop1_atk_buy+flag:shop1_def_buy+flag:shop2_hp_buy+flag:shop2_atk_buy+flag:shop2_def_buy"
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"最高商店购买次数\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "flag:t",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "经验老人购买次数（最高）",
                                                "action": [
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:t",
                                                        "value": "flag:exp1_level_buy + \nflag:exp1_atk_buy + \nflag:exp1_def_buy + \nflag:exp2_level_buy + \nflag:exp2_atk_buy + \nflag:exp2_def_buy"
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"最高经验老人购买次数\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "flag:t",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "存活怪物数量",
                                                "action": [
                                                    {
                                                        "type": "function",
                                                        "function": "function(){\nlet n = 0;\nfor (const f of core.floorIds) {\n\tn += core.searchBlockWithFilter(b => b.event.cls === 'enemys' || b.event.cls === 'enemy48', f).length;\n}\ncore.setFlag('t', n);\n}"
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "flag:rankType",
                                                        "value": "\"存活怪物数量\""
                                                    },
                                                    {
                                                        "type": "setValue",
                                                        "name": "status:hp",
                                                        "value": "flag:t",
                                                        "norefresh": true
                                                    },
                                                    {
                                                        "type": "break",
                                                        "n": 1
                                                    }
                                                ]
                                            },
                                            {
                                                "text": "下一页",
                                                "action": [
                                                    {
                                                        "type": "choices",
                                                        "text": "\t[king]选择要提交的榜单！",
                                                        "choices": [
                                                            {
                                                                "text": "商店购买次数（最低）",
                                                                "action": [
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:t",
                                                                        "value": "flag:shop1_hp_buy+flag:shop1_atk_buy+flag:shop1_def_buy+flag:shop2_hp_buy+flag:shop2_atk_buy+flag:shop2_def_buy"
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:rankType",
                                                                        "value": "\"最低商店购买次数\""
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "status:hp",
                                                                        "value": "flag:t + (10000000000 - 100000*flag:t)",
                                                                        "norefresh": true
                                                                    },
                                                                    {
                                                                        "type": "break",
                                                                        "n": 1
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "text": "经验老人购买次数（最低）",
                                                                "action": [
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:t",
                                                                        "value": "flag:exp1_level_buy + \nflag:exp1_atk_buy + \nflag:exp1_def_buy + \nflag:exp2_level_buy + \nflag:exp2_atk_buy + \nflag:exp2_def_buy"
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:rankType",
                                                                        "value": "\"最低经验老人购买次数\""
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "status:hp",
                                                                        "value": "flag:t + (10000000000 - 100000*flag:t)",
                                                                        "norefresh": true
                                                                    },
                                                                    {
                                                                        "type": "break",
                                                                        "n": 1
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "text": "攻击值（最低）",
                                                                "condition": "false",
                                                                "action": [
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:rankType",
                                                                        "value": "\"最低攻击\""
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "status:hp",
                                                                        "value": "status:atk + (1000000000000 - 1000000*status:atk)",
                                                                        "norefresh": true
                                                                    },
                                                                    {
                                                                        "type": "break",
                                                                        "n": 1
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "text": "防御值（最低）",
                                                                "action": [
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:rankType",
                                                                        "value": "\"最低防御\""
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "status:hp",
                                                                        "value": "status:def + (1000000000000 - 1000000*status:def)",
                                                                        "norefresh": true
                                                                    },
                                                                    {
                                                                        "type": "break",
                                                                        "n": 1
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "text": "攻防和（最低）",
                                                                "action": [
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "flag:rankType",
                                                                        "value": "\"最低攻防和\""
                                                                    },
                                                                    {
                                                                        "type": "setValue",
                                                                        "name": "status:hp",
                                                                        "value": "(status:atk + status:def) + (1000000000000 - 1000000*(status:atk + status:def))",
                                                                        "norefresh": true
                                                                    },
                                                                    {
                                                                        "type": "break",
                                                                        "n": 1
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "text": "上一页",
                                                                "action": []
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "win",
                                "reason": "21层结局（${flag:rankType}）"
                            }
                        ]
                    }
                ]
            },
            {
                "type": "if",
                "condition": "flag:限时",
                "true": [
                    {
                        "type": "function",
                        "function": "function(){\ncore.unregisterAnimationFrame(\"limitTimeFrame\");\ncore.redrawMap();\n}"
                    },
                    {
                        "type": "choices",
                        "text": "\t[作者,king]要继续前进吗？",
                        "choices": [
                            {
                                "text": "继续",
                                "need": "!global:limitTimeUp",
                                "action": []
                            },
                            {
                                "text": "放弃",
                                "action": [
                                    {
                                        "type": "setValue",
                                        "name": "status:hp",
                                        "value": "global:limitTimeLeft"
                                    },
                                    {
                                        "type": "win",
                                        "reason": "娱乐模式",
                                        "norank": 1
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "false": []
            },
            {
                "type": "setBlock",
                "number": "upFloor",
                "loc": [
                    [
                        6,
                        1
                    ]
                ]
            },
            {
                "type": "hide",
                "loc": [
                    [
                        6,
                        7
                    ]
                ],
                "time": 0
            }
        ]
    },
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  0,  0,  4,208,  4,  0,  0,  4,  4,  3],
    [  3,  4,  0,  0,  4,  4,247,  4,  4,  0,  0,  4,  3],
    [  3,  4,  0,  0,  0,  4,247,  4,  0,  0,  0,  4,  3],
    [  3,  4,  4,  0,  0,  0,  0,  0,  0,  0,  4,  4,  3],
    [  3,  4,  4,  0,  0,  0,  0,  0,  0,  0,  4,  4,  3],
    [  3,  4,  4,  4,  0,  0,  4,  0,  0,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4, 86, 88, 86,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  4,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "bgm": "startText.mp3",
    "downFloor": [
        6,
        6
    ],
    "upFloor": [
        6,
        3
    ],
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {}
}