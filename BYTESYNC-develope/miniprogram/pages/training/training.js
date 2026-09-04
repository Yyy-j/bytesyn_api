// pages/training/training.js — 训练首页
// 展示当前周计划和打卡功能，支持日期切换

const { getTrainingTemplate, getOrCreateTrainingWeek, syncCurrentTrainingWeek } = require('../../utils/training-api')
const { getWeekId, getDayIndex, formatLocalDate } = require('../../utils/training-time')

const app = getApp()

// 星期显示文案
const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

Page({
  data: {
    // 页面状态：loading | empty | loaded | error
    state: 'loading',
    // 错误信息
    errorMsg: '',
    // 模板数据
    template: null,
    // 当前周计划
    weekPlan: null,
    weekDocId: '',
    // 日期切换
    dayNames: DAY_NAMES,
    selectedDayIndex: 0,  // 0=周一, 6=周日
    todayDayIndex: 0,
    // 当前日期的训练项目
    currentDayExercises: [],
    // 是否刷新中
    isRefreshing: false,
    // 是否首次加载（用于决定是否重置 selectedDayIndex）
    _isFirstLoad: true
  },

  onLoad() {
    this._loadData()
  },

  onShow() {
    // 每次显示页面时刷新数据，确保同步最新的模板变更
    if (this.data.state !== 'loading') {
      this._loadData(false)  // 非首次加载，保留当前选择的星期
    }
  },

  /**
   * 下拉刷新
   */
  async onPullDownRefresh() {
    if (this.data.isRefreshing) return
    this.setData({ isRefreshing: true })
    try {
      await this._loadData(false)  // 保留当前选择的星期
    } finally {
      this.setData({ isRefreshing: false })
      wx.stopPullDownRefresh()
    }
  },

  /**
   * 加载数据：模板和周计划
   * @param {boolean} resetDay - 是否重置到今天，默认 true（首次加载）
   */
  async _loadData(resetDay = true) {
    this.setData({ state: 'loading', errorMsg: '' })

    try {
      // 等待 app 初始化完成
      await app._initPromise

      // 获取今天是周几
      const todayDayIndex = getDayIndex(new Date())

      // 获取模板
      const templateResult = await getTrainingTemplate()

      if (!templateResult.template) {
        // 无模板
        this.setData({
          state: 'empty',
          template: null,
          todayDayIndex,
          selectedDayIndex: resetDay ? todayDayIndex : this.data.selectedDayIndex,
          _isFirstLoad: false
        })
        return
      }

      // 有模板，同步当前周并使用返回的 week
      const template = templateResult.template
      const templateExerciseCount = (template.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
      console.log('[training] 模板动作数:', templateExerciseCount)

      let weekPlan = null

      // 调用同步确保当前周与模板一致
      try {
        const syncResult = await syncCurrentTrainingWeek()
        console.log('[training] 同步当前周成功')
        // 优先使用同步返回的 week
        if (syncResult && syncResult.week) {
          weekPlan = syncResult.week
        }
      } catch (syncErr) {
        console.error('[training] 同步当前周失败:', syncErr)
        // 同步失败时显示错误，不继续加载旧数据
        this.setData({
          state: 'error',
          errorMsg: syncErr.message || '同步周计划失败，请重试',
          _isFirstLoad: false
        })
        return
      }

      // 如果同步没有返回 week，fallback 到 getOrCreateTrainingWeek
      if (!weekPlan) {
        const weekResult = await getOrCreateTrainingWeek()
        weekPlan = weekResult.week
      }

      // 标准化：确保 days 和 exercises 是数组
      weekPlan.days = Array.isArray(weekPlan.days) ? weekPlan.days : []
      weekPlan.days = weekPlan.days.map(day => ({
        ...day,
        exercises: Array.isArray(day.exercises) ? day.exercises : []
      }))

      const weekExerciseCount = weekPlan.days.reduce((sum, d) => sum + d.exercises.length, 0)
      console.log('[training] 周动作数:', weekExerciseCount, 'weekId:', weekPlan.weekId)

      // 决定选择的星期
      const newSelectedDayIndex = resetDay ? todayDayIndex : this.data.selectedDayIndex

      this.setData({
        state: 'loaded',
        template,
        weekPlan,
        weekDocId: weekPlan._id,
        todayDayIndex,
        selectedDayIndex: newSelectedDayIndex,
        _isFirstLoad: false
      })

      // 更新当日训练项目
      this._updateCurrentDayExercises(newSelectedDayIndex)

    } catch (err) {
      console.error('[training] 加载数据失败', err)
      this.setData({
        state: 'error',
        errorMsg: err.message || '加载失败',
        _isFirstLoad: false
      })
    }
  },

  /**
   * 更新当前日期的训练项目
   */
  _updateCurrentDayExercises(dayIndex) {
    const { weekPlan } = this.data
    if (!weekPlan || !weekPlan.days) {
      this.setData({ currentDayExercises: [] })
      return
    }

    const dayPlan = weekPlan.days.find(d => d.dayIndex === dayIndex)
    // 标准化 exercises 数组
    const exercises = Array.isArray(dayPlan?.exercises) ? dayPlan.exercises : []

    this.setData({ currentDayExercises: exercises })
  },

  /**
   * 切换日期
   */
  onDayChange(e) {
    const dayIndex = parseInt(e.currentTarget.dataset.day, 10)
    if (dayIndex === this.data.selectedDayIndex) return

    this.setData({ selectedDayIndex: dayIndex })
    this._updateCurrentDayExercises(dayIndex)
  },

  /**
   * 重试加载
   */
  onRetry() {
    this._loadData()
  },

  /**
   * 跳转到模板编辑页
   */
  onEditTemplate() {
    this._needRefresh = true
    const hasTemplate = this.data.template ? '1' : '0'
    wx.navigateTo({
      url: `/pages/training-template/training-template?hasTemplate=${hasTemplate}`
    })
  },

  /**
   * 跳转到训练历史页
   */
  onGoHistory() {
    wx.navigateTo({
      url: '/pages/training-history/training-history'
    })
  },

  /**
   * 打卡成功回调，刷新周计划
   */
  async onCheckinSuccess() {
    try {
      const weekResult = await getOrCreateTrainingWeek()
      const weekPlan = weekResult.week
      this.setData({ weekPlan, weekDocId: weekPlan._id })
      this._updateCurrentDayExercises(this.data.selectedDayIndex)
    } catch (err) {
      console.error('[training] 刷新周计划失败', err)
    }
  }
})
