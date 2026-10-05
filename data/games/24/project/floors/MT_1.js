main.floors.MT_1=
{
    "floorId": "MT_1",
    "title": "地 下 层",
    "name": "地 下 层",
    "width": 13,
    "height": 13,
    "canFlyTo": false,
    "canUseQuickShop": false,
    "cannotViewMap": false,
    "images": [],
    "ratio": 1,
    "defaultGround": "ground",
    "bgm": "startText.mp3",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {},
    "changeFloor": {},
    "afterBattle": {
        "6,4": [
            {
                "type": "hide",
                "loc": [
                    [
                        5,
                        2
                    ],
                    [
                        6,
                        2
                    ],
                    [
                        7,
                        2
                    ],
                    [
                        5,
                        3
                    ],
                    [
                        6,
                        3
                    ],
                    [
                        7,
                        3
                    ],
                    [
                        5,
                        4
                    ],
                    [
                        6,
                        4
                    ],
                    [
                        7,
                        4
                    ]
                ],
                "remove": true
            },
            {
                "type": "hideStatusBar"
            },
            {
                "type": "confirm",
                "text": "看剧情？",
                "yes": [
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
                        "reason": "24层结局（${flag:rankType}）"
                    }
                ]
            }
        ]
    },
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3,  5,  5,  5, 86, 86, 86, 86, 86,  5,  5,  5,  3],
    [  3,  5,  5,  5, 86,189,190,191, 86,  5,  5,  5,  3],
    [  3,  5,  5,  5, 86,192,193,194, 86,  5,  5,  5,  3],
    [  3,  5,  5,  5, 86,195,257,196, 86,  5,  5,  5,  3],
    [  3,  5,  5,  5, 86, 86,  0, 86, 86,  5,  5,  5,  3],
    [  3,  5, 32, 32, 32, 32,247, 32, 32, 32, 32,  5,  3],
    [  3,  5,  5,  5,  5,  5,228,  5,  5,  5,  5,  5,  3],
    [  3,  5,  5,  5, 50,228,208,228, 50,  5,  5,  5,  3],
    [  3,  5,  5,  5,  5,  5,228,  5,  5,  5,  5,  5,  3],
    [  3,  5,  5,  5,  5, 32,247, 32,  5,  5,  5,  5,  3],
    [  3,  5,  5,  5,  5,  5,  0,  5,  5,  5,  5,  5,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": null,
    "downFloor": [
        6,
        11
    ],
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {}
}