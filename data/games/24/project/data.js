var data_a1e2fb4a_e986_4524_b0da_9b7ba7c0874d = 
{
	"main": {
		"floorIds": [
			"MT0",
			"MT1",
			"MT2",
			"MT3",
			"MT4",
			"MT5",
			"MT6",
			"MT7",
			"MT8",
			"MT9",
			"MT10",
			"MT11",
			"MT12",
			"MT13",
			"MT14",
			"MT15",
			"MT16",
			"MT17",
			"MT18",
			"MT19",
			"MT20",
			"MT21",
			"MT22",
			"MT23w",
			"MT23e",
			"MT23s",
			"MT_1"
		],
		"floorPartitions": [],
		"images": [
			"VS.png",
			"bear.png",
			"bg.jpg",
			"blueKey.png",
			"brave.png",
			"dragon.png",
			"ground.png",
			"hero.png",
			"redKey.png",
			"title.png",
			"winskin.png",
			"yellowKey.png"
		],
		"tilesets": [
			"magictower.png"
		],
		"animates": [
			"hand",
			"sword",
			"zone"
		],
		"bgms": [
			"title.wav",
			"startText.mp3",
			"prologue.mp3",
			"area1.mp3",
			"area2.mp3",
			"area3.mp3"
		],
		"sounds": [
			"attack.mp3",
			"attack_crit.mp3",
			"battle_win.mp3",
			"blackMagician.mp3",
			"block.mp3",
			"bomb.mp3",
			"brownWizard.mp3",
			"cancel.mp3",
			"centerFly.mp3",
			"confirm.mp3",
			"constants.mp3",
			"cursor.mp3",
			"dialogue.mp3",
			"door.mp3",
			"equip.mp3",
			"error.mp3",
			"floor.mp3",
			"gem.mp3",
			"hurt.mp3",
			"icePickaxe.mp3",
			"item.mp3",
			"jump.mp3",
			"keySold.mp3",
			"keyUnsold.mp3",
			"load.mp3",
			"open_ui.mp3",
			"pickaxe.mp3",
			"queren.mp3",
			"recovery.mp3",
			"redWizard.mp3",
			"save.mp3",
			"shop.mp3",
			"step.mp3",
			"unlockCtrl.mp3",
			"whiteKing.mp3",
			"zone.mp3"
		],
		"fonts": [],
		"nameMap": {
			"确定": "confirm.mp3",
			"取消": "cancel.mp3",
			"操作失败": "error.mp3",
			"光标移动": "cursor.mp3",
			"打开界面": "open_ui.mp3",
			"读档": "load.mp3",
			"存档": "save.mp3",
			"获得道具": "item.mp3",
			"回血": "recovery.mp3",
			"炸弹": "bomb.mp3",
			"飞行器": "centerFly.mp3",
			"开关门": "door.mp3",
			"上下楼": "floor.mp3",
			"跳跃": "jump.mp3",
			"破墙镐": "pickaxe.mp3",
			"破冰镐": "icePickaxe.mp3",
			"宝石": "gem.mp3",
			"阻激夹域": "zone.mp3",
			"穿脱装备": "equip.mp3",
			"背景音乐": "bgm.mp3",
			"攻击": "attack.mp3",
			"暴击": "attack_crit.mp3",
			"受伤": "hurt.mp3",
			"格挡": "block.mp3",
			"战斗胜利": "battle_win.mp3",
			"移动": "step.mp3",
			"商店购买": "queren.mp3",
			"商店离开": "floor.mp3",
			"背景图": "bg.jpg",
			"商店": "shop.mp3",
			"领域": "zone"
		},
		"levelChoose": [],
		"equipName": [
			"武器",
			"盾牌"
		],
		"startBgm": "title.wav",
		"styles": {
			"startBackground": "project/images/title.png",
			"startVerticalBackground": "project/images/title.png",
			"startLogoStyle": "display:none",
			"startButtonsStyle": "background-color: #000000; opacity: 1; color: #FFFFFF; border: #000000 1px solid; caret-color: #FFFFFF;",
			"statusLeftBackground": "url(project/materials/ground.png) repeat",
			"statusTopBackground": "url(project/materials/ground.png) repeat",
			"toolsBackground": "url(project/materials/ground.png) repeat",
			"floorChangingStyle": "background-color: black; color: white",
			"statusBarColor": [
				255,
				255,
				255,
				1
			],
			"borderColor": [
				250,
				118,
				0,
				1
			],
			"selectColor": [
				255,
				215,
				0,
				1
			],
			"font": "Verdana"
		},
		"splitImages": [
			{
				"name": "dragon.png",
				"width": 384,
				"height": 96,
				"prefix": "dragon_"
			}
		]
	},
	"firstData": {
		"title": "24层魔塔",
		"name": "24",
		"version": "Ver 1.12",
		"floorId": "MT0",
		"hero": {
			"image": "hero.png",
			"animate": false,
			"name": "勇士：",
			"lv": 1,
			"hpmax": 9999,
			"hp": 1000,
			"manamax": -1,
			"mana": 0,
			"atk": 10,
			"def": 10,
			"mdef": 0,
			"money": 0,
			"exp": 0,
			"equipment": [],
			"items": {
				"constants": {},
				"tools": {},
				"equips": {}
			},
			"loc": {
				"direction": "up",
				"x": 6,
				"y": 10
			},
			"flags": {},
			"followers": [],
			"steps": 0
		},
		"startCanvas": [
			{
				"type": "comment",
				"text": "在这里可以用事件来自定义绘制标题界面的背景图等"
			},
			{
				"type": "comment",
				"text": "也可以直接切换到其他楼层（比如某个开始剧情楼层）进行操作。"
			},
			{
				"type": "previewUI",
				"action": [
					{
						"type": "fillRect",
						"x": 0,
						"y": 0,
						"width": "core.__PIXELS__",
						"height": "core.__PIXELS__",
						"style": [
							82,
							82,
							82,
							1
						]
					},
					{
						"type": "setAttribute",
						"align": "center"
					},
					{
						"type": "fillBoldText",
						"x": "core.__PIXELS__ / 2",
						"y": 80,
						"style": [
							255,
							255,
							255,
							1
						],
						"strokeStyle": [
							0,
							0,
							0,
							1
						],
						"font": "bold 40px Verdana",
						"text": "${core.firstData.title}"
					}
				]
			},
			{
				"type": "setValue",
				"name": "flag:selection",
				"value": "0"
			},
			{
				"type": "comment",
				"text": "在右下方自绘一个对话框进行显示选择项"
			},
			{
				"type": "previewUI",
				"action": [
					{
						"type": "fillRect",
						"x": 230,
						"y": 250,
						"width": 150,
						"height": 142,
						"radius": 10,
						"style": [
							50,
							54,
							159,
							0.85
						]
					},
					{
						"type": "strokeRect",
						"x": 230,
						"y": 250,
						"width": 150,
						"height": 142,
						"radius": 10,
						"style": [
							255,
							255,
							255,
							1
						],
						"lineWidth": 2
					},
					{
						"type": "fillBoldText",
						"x": 305,
						"y": 290,
						"style": [
							255,
							255,
							255,
							1
						],
						"font": "bold 25px Verdana",
						"text": "开始游戏"
					},
					{
						"type": "fillBoldText",
						"x": 305,
						"y": 330,
						"font": "bold 25px Verdana",
						"text": "读取存档"
					},
					{
						"type": "fillBoldText",
						"x": 305,
						"y": 370,
						"font": "bold 25px Verdana",
						"text": "回放录像"
					}
				]
			},
			{
				"type": "while",
				"condition": "1",
				"data": [
					{
						"type": "drawSelector",
						"image": "winskin.png",
						"code": 1,
						"x": 245,
						"y": "261 + 40*flag:selection",
						"width": 120,
						"height": 40
					},
					{
						"type": "wait",
						"data": [
							{
								"case": "keyboard",
								"keycode": "13,32",
								"break": true,
								"action": [
									{
										"type": "switch",
										"condition": "flag:selection",
										"caseList": [
											{
												"case": "0",
												"action": [
													{
														"type": "comment",
														"text": "在“开始游戏”确定"
													},
													{
														"type": "break",
														"n": 1
													}
												]
											},
											{
												"case": "1",
												"action": [
													{
														"type": "comment",
														"text": "在“读取存档”确定"
													},
													{
														"type": "callLoad"
													}
												]
											},
											{
												"case": "2",
												"action": [
													{
														"type": "comment",
														"text": "在“回放录像”确定"
													},
													{
														"type": "if",
														"condition": "(!core.isReplaying())",
														"true": [
															{
																"type": "function",
																"function": "function(){\ncore.chooseReplayFile()\n}"
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
								"case": "keyboard",
								"keycode": "38",
								"break": true,
								"action": [
									{
										"type": "comment",
										"text": "光标上键"
									},
									{
										"type": "setValue",
										"name": "flag:selection",
										"value": "(flag:selection + 2) % 3"
									}
								]
							},
							{
								"case": "keyboard",
								"keycode": "40",
								"break": true,
								"action": [
									{
										"type": "comment",
										"text": "光标下键"
									},
									{
										"type": "setValue",
										"name": "flag:selection",
										"value": "(flag:selection + 1) % 3"
									}
								]
							},
							{
								"case": "mouse",
								"px": [
									245,
									365
								],
								"py": [
									261,
									300
								],
								"break": true,
								"action": [
									{
										"type": "comment",
										"text": "点击“开始游戏”"
									},
									{
										"type": "break",
										"n": 1
									}
								]
							},
							{
								"case": "mouse",
								"px": [
									245,
									365
								],
								"py": [
									301,
									340
								],
								"break": true,
								"action": [
									{
										"type": "comment",
										"text": "点击“读取存档”"
									},
									{
										"type": "callLoad"
									}
								]
							},
							{
								"case": "mouse",
								"px": [
									245,
									365
								],
								"py": [
									341,
									380
								],
								"break": true,
								"action": [
									{
										"type": "comment",
										"text": "点击“播放录像”"
									},
									{
										"type": "if",
										"condition": "(!core.isReplaying())",
										"true": [
											{
												"type": "function",
												"function": "function(){\ncore.chooseReplayFile()\n}"
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
				"type": "setValue",
				"name": "flag:selection",
				"value": "null"
			},
			{
				"type": "drawSelector",
				"code": 1
			},
			{
				"type": "clearMap"
			},
			{
				"type": "function",
				"function": "function(){\ncore.control.checkBgm()\n}"
			},
			{
				"type": "if",
				"condition": "(main.levelChoose.length == 0)",
				"true": [
					{
						"type": "comment",
						"text": "没有难度选择：直接开始游戏"
					}
				],
				"false": [
					{
						"type": "comment",
						"text": "难度选择：作为样例，这里只提供了一个显示选择项。"
					},
					{
						"type": "function",
						"function": "function(){\nvar choices = [];\nmain.levelChoose.forEach(function (one) {\n\tchoices.push({\n\t\t\"text\": one.title || '',\n\t\t\"action\": [\n\t\t\t{ \"type\": \"function\", \"function\": \"function() { core.status.hard = '\" + (one.name || '') + \"'; }\" }\n\t\t]\n\t});\n})\ncore.insertAction({ \"type\": \"choices\", \"choices\": choices });\n}"
					},
					{
						"type": "comment",
						"text": "你也可以仿照上面的样例进行自己创建等待用户操作来处理不同的难度分歧。\n如需自己处理，请设置 core.status.hard \n（例如，自定义js脚本：core.status.hard = 'Easy' ）"
					}
				]
			},
			{
				"type": "clearMap"
			},
			{
				"type": "comment",
				"text": "接下来会执行startText中的事件"
			},
			{
				"type": "comment",
				"text": "状态栏默认处于隐藏状态；可以使用“显示状态栏”事件进行显示。"
			}
		],
		"startText": [
			{
				"type": "setText",
				"title": [
					255,
					255,
					255,
					1
				],
				"background": [
					0,
					0,
					0,
					1
				]
			},
			{
				"type": "setValue",
				"name": "item:book",
				"value": "1"
			},
			{
				"type": "setValue",
				"name": "flag:fly",
				"value": "false"
			},
			{
				"type": "setValue",
				"name": "flag:移动音效",
				"value": "true"
			},
			{
				"type": "pauseBgm"
			},
			{
				"type": "hideStatusBar"
			},
			{
				"type": "confirm",
				"default": true,
				"text": "是否观看片头？（十秒）",
				"yes": [
					{
						"type": "setVolume",
						"value": 0,
						"time": 0
					},
					{
						"type": "playBgm",
						"name": "startText.mp3"
					},
					{
						"type": "setVolume",
						"value": 100,
						"time": 10000,
						"async": true
					},
					{
						"type": "scrollText",
						"text": "这是一个很古老的故事\n在很久很久以前，在遥远的西方大地上，\n有着这样一个王国，\n王国虽小但全国的人们都生活得非常幸福和快乐。\n突然有一天，从天空飞来一群可怕的怪物，\n它们来到皇宫，抢走了国王唯一的女儿。\n第二天，国王便向全国下达了紧急令，\n只要谁能将公主给找回来，他便将王位让给他。\n于是，全国的勇士们都出发了。\n他们的足迹走遍了全国的各个角落，\n可一点儿线索都没有找到，时间很快就过去了一个月。\n终于，在国王命令下达的第三十一天，\n一个从远方归来的人告诉国王，\n说在海边的一座小岛上，曾看到一群怪物出现过。\n勇士们又出发了，可是，却没有一个人可以回来，\n有幸回来的，都再也不敢去了。\n而我们的故事，便是从这里开始……",
						"time": 10000,
						"lineHeight": 2
					},
					{
						"type": "waitAsync"
					}
				],
				"no": [
					{
						"type": "function",
						"function": "function(){\ncore.addItem('yellowKey');\ncore.addItem('blueKey');\ncore.addItem('redKey');\ncore.hideBlock(6, 9, 'MT0');\ncore.setBlock('fairy', 5, 9, 'MT0')\n}"
					}
				]
			},
			{
				"type": "choices",
				"text": "\t[作者,king]选择模式",
				"choices": [
					{
						"text": "经典模式",
						"action": [
							"\t[作者,king]您可以在工具栏的卷轴中调整战斗动画的速度",
							{
								"type": "setValue",
								"name": "flag:回合间隔",
								"value": "150"
							},
							{
								"type": "setValue",
								"name": "flag:战斗动画",
								"value": "true"
							}
						]
					},
					{
						"text": "极速模式",
						"action": [
							{
								"type": "setValue",
								"name": "item:fly",
								"value": "1"
							},
							"\t[作者,king]您可以在工具栏的卷轴中开启自动操作等功能",
							"\t[作者,king]开局给的楼传为弱化版，仅能在有能到达另一层的路径时才能传送",
							{
								"type": "setValue",
								"name": "flag:开启暴击",
								"value": "false"
							}
						]
					},
					{
						"text": "极速期望暴击版",
						"condition": "false",
						"action": [
							{
								"type": "setValue",
								"name": "item:fly",
								"value": "1"
							},
							"\t[作者,king]开局给的楼传为弱化版，仅能在有能到达另一层的路径时才能传送",
							"\t[作者,king]这个模式将使用数学期望计算伤害，并且注意，当您的勇士生命<=无暴击计算的战损时，无法与怪物交战",
							{
								"type": "setValue",
								"name": "flag:开启暴击",
								"value": "true"
							}
						]
					},
					{
						"text": "限时版",
						"condition": "false",
						"action": [
							{
								"type": "setGlobalFlag",
								"name": "enableMoveDirectly",
								"value": false
							},
							{
								"type": "setValue",
								"name": "flag:限时",
								"value": "true"
							},
							{
								"type": "setValue",
								"name": "item:fly",
								"value": "0"
							},
							{
								"type": "function",
								"function": "function(){\ncore.setGlobal(\"limitTimeLeft\", 16 * 60 * 1000);\ncore.setGlobal(\"limitTimeUp\", false);\ncore.setGlobal(\"limitTimePause\", false);\ncore.setGlobal(\"__limitTimeLast__\", -1);\n\ncore.registerAnimationFrame(\n\t\"limitTimeFrame\",\n\ttrue,\n\tfunction (timestamp) {\n\t\tif (core.getGlobal(\"limitTimeUp\") || core.setGlobal(\"limitTimePause\", false)) return;\n\n\t\tconst last = core.getGlobal(\"__limitTimeLast__\");\n\t\tif (last == null) {\n\t\t\tcore.setGlobal(\"__limitTimeLast__\", timestamp);\n\t\t\treturn;\n\t\t}\n\n\t\tconst delta = timestamp - last;\n\t\tcore.setGlobal(\"__limitTimeLast__\", timestamp);\n\n\t\t// 扣减时间\n\t\tcore.setGlobal(\n\t\t\t\"limitTimeLeft\",\n\t\t\tcore.getGlobal(\"limitTimeLeft\") - delta\n\t\t);\n\n\t\tif (core.getGlobal(\"limitTimeLeft\") <= 0) {\n\t\t\tcore.setGlobal(\"limitTimeLeft\", 0);\n\t\t\tcore.setGlobal(\"limitTimeUp\", true);\n\t\t}\n\n\t\t// ===== 绘制 =====\n\t\tconst ctx = core.createCanvas(\n\t\t\t\"limitTime\",\n\t\t\t0, 0,\n\t\t\t200, 40,\n\t\t\t200\n\t\t);\n\n\t\tcore.clearMap(\"limitTime\");\n\n\t\tconst t = core.getGlobal(\"limitTimeLeft\");\n\t\tconst sec = Math.floor(t / 1000);\n\t\tconst m = Math.floor(sec / 60);\n\t\tconst s = sec % 60;\n\t\tconst text =\n\t\t\tString(m).padStart(2, \"0\") +\n\t\t\t\":\" +\n\t\t\tString(s).padStart(2, \"0\");\n\n\t\tlet color = \"#FFD700\";\n\t\tif (t <= 60 * 1000) color = \"#FF4444\";\n\t\tif (core.getGlobal(\"limitTimeUp\")) color = \"#888888\";\n\t\tcore.fillBoldText(\"limitTime\", \"TIME \" + text, 10, 20, '#FFF', '#000', \"bold 18px Arial\");\n\t}\n);\n}"
							}
						]
					}
				]
			}
		],
		"shops": [
			{
				"id": "moneyShop1",
				"text": "\t[金币商店,moneyShop]想要增加你的能力吗？\n如果你有25个金币，你可以任意选择一项：",
				"textInList": "三楼商店",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "生命+800",
						"need": "status:money>=25",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "25"
							},
							{
								"type": "setValue",
								"name": "status:hp",
								"operator": "+=",
								"value": "800"
							},
							{
								"type": "setValue",
								"name": "flag:shop1_hp_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "攻击+4",
						"need": "status:money>=25",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "25"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "4"
							},
							{
								"type": "setValue",
								"name": "flag:shop1_atk_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "防御+4",
						"need": "status:money>=25",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "25"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "4"
							},
							{
								"type": "setValue",
								"name": "flag:shop1_def_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					}
				]
			},
			{
				"id": "moneyShop2",
				"text": "\t[金币商店,moneyShop]想要增加你的能力吗？\n如果你有100个金币，\n你可以任意选择一项：",
				"textInList": "11楼商店",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "增加4000点生命",
						"need": "status:money>=100",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "100"
							},
							{
								"type": "setValue",
								"name": "status:hp",
								"operator": "+=",
								"value": "4000"
							},
							{
								"type": "setValue",
								"name": "flag:shop2_hp_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加20点攻击",
						"need": "status:money>=100",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "100"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "20"
							},
							{
								"type": "setValue",
								"name": "flag:shop2_atk_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加20点防御",
						"need": "status:money>=100",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "100"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "20"
							},
							{
								"type": "setValue",
								"name": "flag:shop2_def_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					}
				]
			},
			{
				"id": "expShop1",
				"text": "\t[经验老人,man]你好，英雄的人类，只要你有足够的经验，我就可以让你变得更强大：",
				"textInList": "五楼老人",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "提升一级（100）",
						"need": "status:exp>=100",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "100"
							},
							{
								"type": "setValue",
								"name": "status:lv",
								"operator": "+=",
								"value": "1"
							},
							{
								"type": "setValue",
								"name": "status:hp",
								"operator": "+=",
								"value": "1000"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "7"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "7"
							},
							{
								"type": "setValue",
								"name": "flag:exp1_level_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加攻击5（30）",
						"need": "status:exp>=30",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "30"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "5"
							},
							{
								"type": "setValue",
								"name": "flag:exp1_atk_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加防御5（30）",
						"need": "status:exp>=30",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "30"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "5"
							},
							{
								"type": "setValue",
								"name": "flag:exp1_def_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					}
				]
			},
			{
				"id": "expShop2",
				"text": "\t[经验老人,man]你好，英雄的人类，只要你有足够的经验，我就可以让你变得更强大：",
				"textInList": "13楼老人",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "提升三级（270）",
						"need": "status:exp>=270",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "270"
							},
							{
								"type": "setValue",
								"name": "status:lv",
								"operator": "+=",
								"value": "3"
							},
							{
								"type": "setValue",
								"name": "status:hp",
								"operator": "+=",
								"value": "3000"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "20"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "20"
							},
							{
								"type": "setValue",
								"name": "flag:exp2_level_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加攻击17（95）",
						"need": "status:exp>=95",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "95"
							},
							{
								"type": "setValue",
								"name": "status:atk",
								"operator": "+=",
								"value": "17"
							},
							{
								"type": "setValue",
								"name": "flag:exp2_atk_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "增加防御17（95）",
						"need": "status:exp>=95",
						"action": [
							{
								"type": "setValue",
								"name": "status:exp",
								"operator": "-=",
								"value": "95"
							},
							{
								"type": "setValue",
								"name": "status:def",
								"operator": "+=",
								"value": "17"
							},
							{
								"type": "setValue",
								"name": "flag:exp2_def_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					}
				]
			},
			{
				"id": "keyShop1",
				"text": "\t[购入钥匙,trader]相信你一定有特殊的需要，只要你有金币，我就可以帮你：",
				"textInList": "购入钥匙",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "购买1把黄钥匙（10）",
						"need": "status:money>=10",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "10"
							},
							{
								"type": "setValue",
								"name": "item:yellowKey",
								"operator": "+=",
								"value": "1"
							},
							{
								"type": "setValue",
								"name": "flag:keyshop1_yellow_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "购买1把蓝钥匙（50）",
						"need": "status:money>=50",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "50"
							},
							{
								"type": "setValue",
								"name": "item:blueKey",
								"operator": "+=",
								"value": "1"
							},
							{
								"type": "setValue",
								"name": "flag:keyshop1_blue_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					},
					{
						"text": "购买1把红钥匙（100）",
						"need": "status:money>=100",
						"action": [
							{
								"type": "setValue",
								"name": "status:money",
								"operator": "-=",
								"value": "100"
							},
							{
								"type": "setValue",
								"name": "item:redKey",
								"operator": "+=",
								"value": "1"
							},
							{
								"type": "setValue",
								"name": "flag:keyshop1_red_buy",
								"operator": "+=",
								"value": "1"
							}
						]
					}
				]
			},
			{
				"id": "keyShop2",
				"text": "\t[商人,trader]哦，欢迎你的到来，如果你手里缺少金币，我可以帮你：",
				"textInList": "出售钥匙",
				"mustEnable": false,
				"disablePreview": true,
				"choices": [
					{
						"text": "卖出一把黄钥匙（7）",
						"need": "true",
						"action": [
							{
								"type": "if",
								"condition": "(item:yellowKey >= 1)",
								"true": [
									{
										"type": "setValue",
										"name": "item:yellowKey",
										"operator": "-=",
										"value": "1"
									},
									{
										"type": "setValue",
										"name": "status:money",
										"operator": "+=",
										"value": "7"
									},
									{
										"type": "setValue",
										"name": "flag:keyshop2_yellow_sell",
										"operator": "+=",
										"value": "1"
									}
								],
								"false": [
									"\t[商人,trader]你没有黄钥匙！"
								]
							}
						]
					},
					{
						"text": "卖出一把蓝钥匙（35）",
						"need": "true",
						"action": [
							{
								"type": "if",
								"condition": "(item:blueKey >= 1)",
								"true": [
									{
										"type": "setValue",
										"name": "item:blueKey",
										"operator": "-=",
										"value": "1"
									},
									{
										"type": "setValue",
										"name": "status:money",
										"operator": "+=",
										"value": "35"
									},
									{
										"type": "setValue",
										"name": "flag:keyshop2_blue_sell",
										"operator": "+=",
										"value": "1"
									}
								],
								"false": [
									"\t[商人,trader]你没有蓝钥匙！"
								]
							}
						]
					},
					{
						"text": "卖出一把红钥匙（70）",
						"need": "true",
						"action": [
							{
								"type": "if",
								"condition": "(item:redKey>= 1)",
								"true": [
									{
										"type": "setValue",
										"name": "item:redKey",
										"operator": "-=",
										"value": "1"
									},
									{
										"type": "setValue",
										"name": "status:money",
										"operator": "+=",
										"value": "70"
									},
									{
										"type": "setValue",
										"name": "flag:keyshop2_red_sell",
										"operator": "+=",
										"value": "1"
									}
								],
								"false": [
									"\t[商人,trader]你没有红钥匙！"
								]
							}
						]
					}
				]
			}
		],
		"levelUp": [
			{
				"need": "0",
				"title": "",
				"action": [
					{
						"type": "comment",
						"text": "此处是初始等级，只需填写称号"
					}
				]
			},
			{
				"need": "20",
				"title": "",
				"action": [
					{
						"type": "setValue",
						"name": "status:atk",
						"operator": "+=",
						"value": "10"
					},
					{
						"type": "setValue",
						"name": "status:def",
						"operator": "+=",
						"value": "10"
					}
				]
			},
			{
				"need": "40",
				"title": "",
				"action": [
					{
						"type": "tip",
						"text": "恭喜升级"
					}
				]
			}
		]
	},
	"values": {
		"lavaDamage": 100,
		"poisonDamage": 10,
		"weakValue": 20,
		"redGem": 3,
		"blueGem": 3,
		"greenGem": 5,
		"redPotion": 200,
		"bluePotion": 500,
		"yellowPotion": 500,
		"greenPotion": 800,
		"breakArmor": 0.9,
		"counterAttack": 0.1,
		"purify": 3,
		"hatred": 2,
		"animateSpeed": 300,
		"moveSpeed": 100,
		"statusCanvasRowsOnMobile": 3,
		"floorChangeTime": 500
	},
	"flags": {
		"statusBarItems": [
			"enableFloor",
			"enableLv",
			"enableHP",
			"enableAtk",
			"enableDef",
			"enableMoney",
			"enableExp",
			"enableKeys"
		],
		"extendToolbar": true,
		"flyNearStair": false,
		"flyRecordPosition": false,
		"itemFirstText": false,
		"equipboxButton": false,
		"enableAddPoint": false,
		"enableNegativeDamage": false,
		"betweenAttackMax": false,
		"useLoop": true,
		"startUsingCanvas": false,
		"statusCanvas": true,
		"enableEnemyPoint": true,
		"enableGentleClick": false,
		"ignoreChangeFloor": false,
		"canGoDeadZone": false,
		"enableMoveDirectly": true,
		"enableRouteFolding": false,
		"disableShopOnDamage": false,
		"blurFg": false,
		"autoScale": null,
		"hideLeftStatusBar": null
	}
}