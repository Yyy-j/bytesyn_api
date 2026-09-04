// pages/training-webview/training-webview.js — 视频 WebView 页
// 在内嵌浏览器中显示视频页面

Page({
  data: {
    url: '',
    title: ''
  },

  onLoad(options) {
    const { url, title } = options
    
    // 校验 URL
    if (!url) {
      wx.showToast({ title: 'URL参数缺失', icon: 'none' })
      wx.navigateBack()
      return
    }

    const decodedUrl = decodeURIComponent(url)
    
    // 仅允许 HTTPS
    if (!decodedUrl.startsWith('https://') && !decodedUrl.startsWith('http://')) {
      wx.showToast({ title: '仅支持 http/https 链接', icon: 'none' })
      wx.navigateBack()
      return
    }

    const decodedTitle = title ? decodeURIComponent(title) : '教学视频'
    
    this.setData({
      url: decodedUrl,
      title: decodedTitle
    })

    // 设置页面标题
    wx.setNavigationBarTitle({ title: decodedTitle })
  },

  /**
   * 复制链接
   */
  onCopyUrl() {
    wx.setClipboardData({
      data: this.data.url,
      success: () => {
        wx.showToast({ title: '链接已复制', icon: 'success' })
      }
    })
  },

  /**
   * 用系统浏览器打开
   */
  onOpenInBrowser() {
    // 微信小程序不支持直接打开系统浏览器
    // 提示用户复制链接
    wx.showModal({
      title: '提示',
      content: '小程序内无法直接打开系统浏览器，请复制链接后在浏览器中打开',
      confirmText: '复制链接',
      success: (res) => {
        if (res.confirm) {
          this.onCopyUrl()
        }
      }
    })
  },

  /**
   * WebView 加载错误
   */
  onError(e) {
    console.error('[training-webview] 加载失败', e)
    wx.showToast({ title: '页面加载失败', icon: 'none' })
  }
})
