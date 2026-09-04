// pages/pairing/pairing.js
const { createPair, createUser, joinPair } = require('../../utils/api')

const app = getApp()

Page({
  data: {
    ready:      false,
    state:      'init',  // 'init' | 'created' | 'join'
    inviteCode: '',
    pairId:     '',
    inputCode:  '',
    loading:    false,
  },

  onLoad() {
    // 等待 app 初始化完成再决定跳转还是展示
    app._initPromise.then(() => {
      if (app.globalData.pairId) {
        // 已配对，直接进 summary
        wx.switchTab({ url: '/pages/summary/summary' })
        return
      }
      this.setData({ ready: true })
    })
  },

  // ── 创建配对（用户 A）────────────────────────────────
  onCreate() {
    if (this.data.loading) return
    const { openid } = app.globalData
    if (!openid) {
      wx.showToast({ title: '初始化中，请稍候', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    wx.showLoading({ title: '创建中…', mask: true })

    createPair({ creatorOpenId: openid })
      .then(({ pairId, inviteCode }) =>
        createUser({ openid, role: 'me', userName: '我', pairId })
          .then(() => {
            // 更新全局状态
            app.globalData.pairId = pairId
            app.globalData.userProfile = { openid, role: 'me', userName: '我', pairId }
            wx.hideLoading()
            this.setData({ state: 'created', inviteCode, pairId, loading: false })
          })
      )
      .catch(err => {
        wx.hideLoading()
        console.error('[pairing] 创建失败', err)
        this.setData({ loading: false })
        wx.showToast({ title: '创建失败，请重试', icon: 'none' })
      })
  },

  // ── 切换到输入邀请码界面 ──────────────────────────────
  toJoin() {
    this.setData({ state: 'join', inputCode: '' })
  },

  toInit() {
    this.setData({ state: 'init' })
  },

  onCodeInput(e) {
    this.setData({ inputCode: e.detail.value })
  },

  // ── 加入配对（用户 B）────────────────────────────────
  onJoin() {
    if (this.data.loading) return
    const { inputCode } = this.data
    const { openid } = app.globalData

    if (!inputCode || inputCode.trim().length < 6) {
      wx.showToast({ title: '请输入完整邀请码', icon: 'none' })
      return
    }
    if (!openid) {
      wx.showToast({ title: '初始化中，请稍候', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    wx.showLoading({ title: '加入中…', mask: true })

    joinPair({ openid, inviteCode: inputCode.trim() })
      .then(({ pairId }) =>
        createUser({ openid, role: 'ta', userName: 'Ta', pairId })
          .then(() => {
            app.globalData.pairId = pairId
            app.globalData.userProfile = { openid, role: 'ta', userName: 'Ta', pairId }
            wx.hideLoading()
            this.setData({ loading: false })
            wx.showToast({ title: '配对成功！', icon: 'success', duration: 1500 })
            setTimeout(() => {
              wx.switchTab({ url: '/pages/summary/summary' })
            }, 1500)
          })
      )
      .catch(err => {
        wx.hideLoading()
        console.error('[pairing] 加入失败', err)
        this.setData({ loading: false })
        wx.showToast({ title: err.message || '加入失败，请重试', icon: 'none' })
      })
  },

  // ── 创建后直接进入 summary ───────────────────────────
  goToSummary() {
    wx.switchTab({ url: '/pages/summary/summary' })
  },
})
