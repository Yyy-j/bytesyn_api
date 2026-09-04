// utils/config.js — 全局配置（Step 7 替换为动态值）

module.exports = {
  // ── 云开发环境 ID ──
  // 在微信开发者工具「云开发控制台」右上角查看，格式如 "xxx-yyy-zzz"
  cloudEnvId: 'cloud1-5gpu3nmc673b62c2',

  // ── 配对 & 用户（Step 7 接入登录后替换为真实 openId）──
  pairId:     'demo_pair',
  myUserId:   'demo_user_1',
  taUserId:   'demo_user_2',
  myUserName: '我',
  taUserName: 'Ta',

  // ── 每日营养目标（Step 7 可改为个人配置）──
  goals: {
    me: { calorieGoal: 2000, proteinGoal: 90, carbsGoal: 250, fatGoal: 60 },
    ta: { calorieGoal: 2000, proteinGoal: 90, carbsGoal: 250, fatGoal: 60 },
  },
}
