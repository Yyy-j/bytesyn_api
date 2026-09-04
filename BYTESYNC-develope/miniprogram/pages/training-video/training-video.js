// pages/training-video/training-video.js — 教学视频管理页
// 管理视频链接，支持 customExercise 和 templateItem 两种范围

const { addTrainingVideo, updateTrainingVideo, deleteTrainingVideo } = require('../../utils/training-api')

Page({
  data: {
    // 参数
    scopeType: '',  // customExercise | templateItem
    scopeId: '',
    
    // 页面状态
    state: 'ready',  // ready | saving
    
    // 视频列表 (最多3个)
    videoLinks: [],
    
    // 添加/编辑表单
    showForm: false,
    isEditing: false,
    editingIndex: -1,
    formTitle: '',
    formUrl: ''
  },

  onLoad(options) {
    const { scopeType, scopeId } = options
    if (!scopeType || !scopeId) {
      wx.showToast({ title: '参数错误', icon: 'none' })
      wx.navigateBack()
      return
    }
    
    this.setData({ scopeType, scopeId })
    
    // 通过 eventChannel 接收当前 videoLinks
    const eventChannel = this.getOpenerEventChannel()
    if (eventChannel && eventChannel.on) {
      eventChannel.on('sendVideoLinks', (data) => {
        const videoLinks = Array.isArray(data.videoLinks) ? data.videoLinks : []
        this.setData({ videoLinks })
      })
    }
  },

  onUnload() {
    // 返回时通过 eventChannel 发送更新后的 videoLinks
    const eventChannel = this.getOpenerEventChannel()
    if (eventChannel && eventChannel.emit) {
      eventChannel.emit('videoLinksChanged', { videoLinks: this.data.videoLinks })
    }
  },

  /**
   * 显示添加表单
   */
  onShowAddForm() {
    if (this.data.videoLinks.length >= 3) {
      wx.showToast({ title: '最多添加3个视频', icon: 'none' })
      return
    }
    this.setData({
      showForm: true,
      isEditing: false,
      editingIndex: -1,
      formTitle: '',
      formUrl: ''
    })
  },

  /**
   * 显示编辑表单
   */
  onShowEditForm(e) {
    const index = e.currentTarget.dataset.index
    const video = this.data.videoLinks[index]
    if (!video) return
    
    this.setData({
      showForm: true,
      isEditing: true,
      editingIndex: index,
      formTitle: video.title || '',
      formUrl: video.url || ''
    })
  },

  /**
   * 隐藏表单
   */
  onHideForm() {
    this.setData({
      showForm: false,
      isEditing: false,
      editingIndex: -1,
      formTitle: '',
      formUrl: ''
    })
  },

  /**
   * 弹窗内容点击（阻止冒泡）
   */
  onFormPopupTap() {
    // 阻止事件冒泡到遮罩层
  },

  /**
   * 输入标题
   */
  onTitleInput(e) {
    this.setData({ formTitle: e.detail.value })
  },

  /**
   * 输入URL
   */
  onUrlInput(e) {
    this.setData({ formUrl: e.detail.value })
  },

  /**
   * 校验URL
   */
  _validateUrl(url) {
    if (!url || typeof url !== 'string') {
      return { valid: false, error: '请输入URL' }
    }
    const trimmed = url.trim()
    if (!trimmed.startsWith('https://') && !trimmed.startsWith('http://')) {
      return { valid: false, error: 'URL必须以 http:// 或 https:// 开头' }
    }
    // 检查重复
    const { videoLinks, isEditing, editingIndex } = this.data
    const isDuplicate = videoLinks.some((v, i) => {
      if (isEditing && i === editingIndex) return false
      return v.url === trimmed
    })
    if (isDuplicate) {
      return { valid: false, error: 'URL已存在' }
    }
    return { valid: true, url: trimmed }
  },

  /**
   * 保存表单（添加或更新）
   */
  async onSaveForm() {
    if (this.data.state === 'saving') return

    const { formTitle, formUrl, scopeType, scopeId, isEditing, editingIndex, videoLinks } = this.data
    
    // 校验标题
    const title = formTitle.trim()
    if (!title) {
      wx.showToast({ title: '请输入视频标题', icon: 'none' })
      return
    }
    if (title.length > 50) {
      wx.showToast({ title: '标题不能超过50字符', icon: 'none' })
      return
    }

    // 校验URL
    const urlResult = this._validateUrl(formUrl)
    if (!urlResult.valid) {
      wx.showToast({ title: urlResult.error, icon: 'none' })
      return
    }

    this.setData({ state: 'saving' })

    try {
      if (isEditing) {
        // 更新视频
        const video = videoLinks[editingIndex]
        await updateTrainingVideo({
          scopeType,
          scopeId,
          videoId: video.videoId,
          title,
          url: urlResult.url
        })
        
        // 更新本地数据
        const newLinks = [...videoLinks]
        newLinks[editingIndex] = { ...video, title, url: urlResult.url }
        this.setData({ videoLinks: newLinks })
        
        wx.showToast({ title: '更新成功', icon: 'success' })
      } else {
        // 添加视频
        const result = await addTrainingVideo({
          scopeType,
          scopeId,
          title,
          url: urlResult.url
        })
        
        // 添加到本地数据
        const newVideo = {
          videoId: result.videoId,
          title,
          url: urlResult.url
        }
        this.setData({ videoLinks: [...videoLinks, newVideo] })
        
        wx.showToast({ title: '添加成功', icon: 'success' })
      }

      this.onHideForm()
    } catch (err) {
      console.error('[training-video] 保存失败', err)
      wx.showToast({ title: err.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ state: 'ready' })
    }
  },

  /**
   * 删除视频
   */
  onDeleteVideo(e) {
    const index = e.currentTarget.dataset.index
    const video = this.data.videoLinks[index]
    if (!video) return

    wx.showModal({
      title: '确认删除',
      content: `确定删除视频「${video.title}」吗？`,
      success: async (res) => {
        if (!res.confirm) return

        this.setData({ state: 'saving' })
        try {
          await deleteTrainingVideo({
            scopeType: this.data.scopeType,
            scopeId: this.data.scopeId,
            videoId: video.videoId
          })

          // 从本地数据删除
          const newLinks = this.data.videoLinks.filter((_, i) => i !== index)
          this.setData({ videoLinks: newLinks })

          wx.showToast({ title: '删除成功', icon: 'success' })
        } catch (err) {
          console.error('[training-video] 删除失败', err)
          wx.showToast({ title: err.message || '删除失败', icon: 'none' })
        } finally {
          this.setData({ state: 'ready' })
        }
      }
    })
  },

  /**
   * 打开视频（跳转 webview）
   */
  onOpenVideo(e) {
    const index = e.currentTarget.dataset.index
    const video = this.data.videoLinks[index]
    if (!video || !video.url) return

    wx.navigateTo({
      url: `/pages/training-webview/training-webview?url=${encodeURIComponent(video.url)}&title=${encodeURIComponent(video.title || '教学视频')}`
    })
  }
})
