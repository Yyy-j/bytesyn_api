// pages/training-exercise/training-exercise.js — 动作选择页
// 展示固定动作和自定义动作，支持搜索、筛选和创建

const { 
  getAllExercises, 
  getAllCategories, 
  searchExercises 
} = require('../../utils/training-exercises')

const { 
  getCustomExercises, 
  createCustomExercise 
} = require('../../utils/training-api')

const app = getApp()

Page({
  data: {
    // 页面状态
    state: 'loading',  // loading | ready | error
    errorMsg: '',
    
    // 分类
    categories: [],
    selectedCategory: '',  // 空字符串表示全部
    
    // 搜索关键词
    searchKeyword: '',
    
    // 动作列表
    fixedExercises: [],
    customExercises: [],
    filteredExercises: [],
    
    // 当前显示的 tab
    currentTab: 'fixed',  // fixed | custom
    
    // 自定义动作表单
    showCreateForm: false,
    createForm: {
      name: '',
      category: '其他',
      itemType: 'strength',
      defaultSets: '4',
      defaultReps: '12',
      defaultWeight: '',
      defaultDuration: '30'
    },
    isCreating: false
  },

  onLoad() {
    this._loadData()
  },

  /**
   * 加载数据
   */
  async _loadData() {
    this.setData({ state: 'loading', errorMsg: '' })

    try {
      await app._initPromise

      // 加载固定动作
      const fixedExercises = getAllExercises()
      const categories = getAllCategories()

      // 加载自定义动作
      let customExercises = []
      try {
        const result = await getCustomExercises()
        customExercises = result.exercises || []
      } catch (err) {
        console.warn('[training-exercise] 加载自定义动作失败', err)
        // 不影响页面显示
      }

      this.setData({
        state: 'ready',
        categories,
        fixedExercises,
        customExercises,
        filteredExercises: fixedExercises
      })
    } catch (err) {
      console.error('[training-exercise] 加载数据失败', err)
      this.setData({
        state: 'error',
        errorMsg: err.message || '加载失败'
      })
    }
  },

  /**
   * 切换 Tab
   */
  onTabChange(e) {
    const tab = e.currentTarget.dataset.tab
    if (tab === this.data.currentTab) return

    this.setData({
      currentTab: tab,
      selectedCategory: '',
      searchKeyword: ''
    })
    this._filterExercises()
  },

  /**
   * 搜索输入
   */
  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value })
    this._filterExercises()
  },

  /**
   * 清除搜索
   */
  onClearSearch() {
    this.setData({ searchKeyword: '' })
    this._filterExercises()
  },

  /**
   * 选择分类
   */
  onCategoryChange(e) {
    const category = e.currentTarget.dataset.category
    const newCategory = category === this.data.selectedCategory ? '' : category
    this.setData({ selectedCategory: newCategory })
    this._filterExercises()
  },

  /**
   * 筛选动作
   */
  _filterExercises() {
    const { currentTab, fixedExercises, customExercises, selectedCategory, searchKeyword } = this.data
    
    // 选择数据源
    let exercises = currentTab === 'fixed' ? fixedExercises : customExercises
    
    // 分类筛选
    if (selectedCategory) {
      exercises = exercises.filter(ex => ex.category === selectedCategory)
    }
    
    // 关键词搜索
    if (searchKeyword.trim()) {
      const keyword = searchKeyword.toLowerCase().trim()
      exercises = exercises.filter(ex => {
        const nameMatch = (ex.name || '').toLowerCase().includes(keyword)
        const englishMatch = (ex.englishName || '').toLowerCase().includes(keyword)
        return nameMatch || englishMatch
      })
    }
    
    this.setData({ filteredExercises: exercises })
  },

  /**
   * 选择动作
   */
  onSelectExercise(e) {
    const exercise = e.currentTarget.dataset.exercise

    // 自定义动作始终返回 sourceType: 'custom'
    // 根据当前 tab 或数据判断来源类型
    const isCustom = this.data.currentTab === 'custom' || exercise.sourceType === 'custom'

    // 构建返回数据
    const returnData = {
      exerciseId: exercise.id || exercise._id,
      exerciseName: exercise.name,
      sourceType: isCustom ? 'custom' : 'fixed',
      itemType: exercise.itemType || 'strength',
      category: exercise.category || '',
      targetSets: exercise.defaultSets || 4,
      targetReps: exercise.defaultReps || 12,
      targetWeight: exercise.defaultWeight || 0,
      targetDuration: exercise.defaultDuration || 0,
      videoLinks: exercise.videoLinks || [],
      order: 0
    }
    
    // 通过 eventChannel 返回数据
    const eventChannel = this.getOpenerEventChannel()
    if (eventChannel && eventChannel.emit) {
      eventChannel.emit('selectExercise', returnData)
    }
    
    wx.navigateBack()
  },

  /**
   * 显示创建表单
   */
  onShowCreateForm() {
    this.setData({
      showCreateForm: true,
      createForm: {
        name: '',
        category: '其他',
        itemType: 'strength',
        defaultSets: '4',
        defaultReps: '12',
        defaultWeight: '',
        defaultDuration: '30'
      }
    })
  },

  /**
   * 隐藏创建表单
   */
  onHideCreateForm() {
    this.setData({ showCreateForm: false })
  },

  /**
   * 弹窗内容点击（阻止冒泡）
   */
  onModalContentTap() {
    // 阻止事件冒泡到遮罩层
  },

  /**
   * 创建表单输入
   */
  onCreateFormInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`createForm.${field}`]: e.detail.value })
  },

  /**
   * 选择动作类型
   */
  onItemTypeChange(e) {
    const type = e.currentTarget.dataset.type
    if (type === 'strength' || type === 'cardio') {
      this.setData({ 'createForm.itemType': type })
    }
  },

  /**
   * 创建自定义动作
   */
  async onCreateExercise() {
    if (this.data.isCreating) return
    
    const { createForm } = this.data
    
    // 验证名称
    const name = createForm.name.trim()
    if (!name) {
      wx.showToast({ title: '请输入动作名称', icon: 'none' })
      return
    }
    
    // 构建数据
    const exerciseData = {
      name,
      category: createForm.category || '其他',
      itemType: createForm.itemType
    }
    
    if (createForm.itemType === 'cardio') {
      const duration = Number(createForm.defaultDuration)
      if (isNaN(duration) || duration < 1 || duration > 1440) {
        wx.showToast({ title: '时长需在 1-1440 秒之间', icon: 'none' })
        return
      }
      exerciseData.defaultDuration = duration
    } else {
      const sets = Number(createForm.defaultSets)
      const reps = Number(createForm.defaultReps)
      const weight = Number(createForm.defaultWeight) || 0
      
      if (isNaN(sets) || sets < 1 || sets > 50) {
        wx.showToast({ title: '组数需在 1-50 之间', icon: 'none' })
        return
      }
      if (isNaN(reps) || reps < 1 || reps > 999) {
        wx.showToast({ title: '次数需在 1-999 之间', icon: 'none' })
        return
      }
      
      exerciseData.defaultSets = sets
      exerciseData.defaultReps = reps
      exerciseData.defaultWeight = weight
    }
    
    this.setData({ isCreating: true })
    
    try {
      const result = await createCustomExercise(exerciseData)
      
      // 创建成功，添加到列表
      const newExercise = {
        _id: result.exerciseId,
        id: result.exerciseId,
        ...exerciseData,
        sourceType: 'custom',
        videoLinks: []
      }
      
      const customExercises = [newExercise, ...this.data.customExercises]
      
      this.setData({
        customExercises,
        showCreateForm: false,
        isCreating: false,
        // 切换到自定义 tab 并刷新
        currentTab: 'custom',
        filteredExercises: customExercises
      })
      
      wx.showToast({ title: '创建成功', icon: 'success' })
      
    } catch (err) {
      console.error('[training-exercise] 创建动作失败', err)
      wx.showToast({ title: err.message || '创建失败', icon: 'none' })
      this.setData({ isCreating: false })
    }
  },

  /**
   * 管理自定义动作的教学视频
   */
  onManageExerciseVideos(e) {
    const exercise = e.currentTarget.dataset.exercise
    if (!exercise || !exercise._id) return

    const that = this
    wx.navigateTo({
      url: `/pages/training-video/training-video?scopeType=customExercise&scopeId=${exercise._id}`,
      events: {
        // 接收视频链接变更
        videoLinksChanged(data) {
          that._updateCustomExerciseVideoLinks(exercise._id, data.videoLinks || [])
        }
      },
      success(res) {
        // 发送当前视频链接
        res.eventChannel.emit('sendVideoLinks', {
          videoLinks: exercise.videoLinks || []
        })
      }
    })
  },

  /**
   * 更新自定义动作的视频链接
   */
  _updateCustomExerciseVideoLinks(exerciseId, videoLinks) {
    const customExercises = this.data.customExercises.map(ex => {
      if (ex._id === exerciseId || ex.id === exerciseId) {
        return { ...ex, videoLinks }
      }
      return ex
    })

    this.setData({ customExercises })

    // 如果当前显示的是自定义动作，更新筛选列表
    if (this.data.currentTab === 'custom') {
      this._filterExercises()
    }
  },

  /**
   * 重试加载
   */
  onRetry() {
    this._loadData()
  }
})
