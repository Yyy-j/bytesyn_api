// app.js
const config = require('./utils/config')
const { getOpenId, getUserByOpenId } = require('./utils/api')

App({
  globalData: {
    openid:      '',
    userProfile: null,   // { openid, role, userName, pairId }
    pairId:      '',
  },

  onLaunch() {
    if (!wx.cloud) {
      console.error('[BiteSync] 请升级基础库至 2.2.3+ 以使用云开发')
      this._initPromise = Promise.resolve()
      return
    }

    wx.cloud.init({ env: config.cloudEnvId, traceUser: true })

    // _initPromise：pages 调用 app._initPromise.then() 等待初始化完成
    this._initPromise = getOpenId()
      .then(res => {
        this.globalData.openid = res.openid
        return getUserByOpenId(res.openid)
      })
      .then(res => {
        if (res.data && res.data.length > 0) {
          const profile = res.data[0]
          this.globalData.userProfile = profile
          this.globalData.pairId = profile.pairId || ''
        }
        // 用户不存在时暂不处理，由 pairing 页面完成注册
      })
      .catch(err => {
        console.error('[BiteSync] 初始化失败', err)
        // catch 防止 pages 的 .then() 永远挂起
      })
  },
})

