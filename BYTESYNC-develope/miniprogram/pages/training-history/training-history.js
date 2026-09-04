// pages/training-history/training-history.js — 训练历史页面
// 展示历史周计划和打卡记录，按周倒序，支持展开查看

const { getTrainingWeekHistory } = require('../../utils/training-api')

const app = getApp()

// 星期显示文案
const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const PAGE_SIZE = 10

Page({
  data: {
    // 页面状态：loading | empty | loaded | error
    state: 'loading',
    errorMsg: '',
    // 历史周列表
    weeks: [],
    // 已加载的周 ID 集合（去重用）
    loadedWeekIds: {},
    // 展开的周索引
    expandedWeekIndex: -1,
    // 分页
    offset: 0,
    hasMore: true,
    isLoadingMore: false,
    // 星期名称
    dayNames: DAY_NAMES
  },

  onLoad() {
    this._loadHistory()
  },

  /**
   * 加载历史数据
   */
  async _loadHistory() {
    this.setData({ state: 'loading', errorMsg: '' })

    try {
      await app._initPromise

      const result = await getTrainingWeekHistory({ limit: PAGE_SIZE, offset: 0 })
      const weeks = result.weeks || []

      // 构建去重 map
      const loadedWeekIds = {}
      weeks.forEach(w => { loadedWeekIds[w._id] = true })

      // 判断是否还有更多（以返回数量小于 limit 为准）
      const hasMore = weeks.length >= PAGE_SIZE

      this.setData({
        state: weeks.length > 0 ? 'loaded' : 'empty',
        weeks: this._processWeeks(weeks),
        loadedWeekIds,
        offset: weeks.length,
        hasMore
      })

    } catch (err) {
      console.error('[training-history] 加载历史失败', err)
      this.setData({
        state: 'error',
        errorMsg: err.message || '加载失败'
      })
    }
  },

  /**
   * 加载更多
   */
  async onLoadMore() {
    if (this.data.isLoadingMore || !this.data.hasMore) return

    this.setData({ isLoadingMore: true })

    try {
      const result = await getTrainingWeekHistory({
        limit: PAGE_SIZE,
        offset: this.data.offset
      })

      const newWeeks = result.weeks || []

      // 按 _id 去重
      const loadedWeekIds = { ...this.data.loadedWeekIds }
      const filteredWeeks = newWeeks.filter(w => {
        if (loadedWeekIds[w._id]) return false
        loadedWeekIds[w._id] = true
        return true
      })

      // 判断是否还有更多
      const hasMore = newWeeks.length >= PAGE_SIZE

      this.setData({
        weeks: [...this.data.weeks, ...this._processWeeks(filteredWeeks)],
        loadedWeekIds,
        offset: this.data.offset + newWeeks.length,
        hasMore
      })

    } catch (err) {
      console.error('[training-history] 加载更多失败', err)
      wx.showToast({ title: err.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ isLoadingMore: false })
    }
  },

  /**
   * 处理周数据：计算完成组数和目标组数
   */
  _processWeeks(weeks) {
    return weeks.map(week => {
      let totalCompleted = 0
      let totalTarget = 0

      if (week.days && Array.isArray(week.days)) {
        week.days.forEach(day => {
          if (day.exercises && Array.isArray(day.exercises)) {
            day.exercises.forEach(ex => {
              totalCompleted += ex.completedSets || 0
              totalTarget += ex.targetSets || 0
            })
          }
        })
      }

      return {
        ...week,
        totalCompleted,
        totalTarget
      }
    })
  },

  /**
   * 展开/收起周详情
   */
  onToggleWeek(e) {
    const index = e.currentTarget.dataset.index
    this.setData({
      expandedWeekIndex: this.data.expandedWeekIndex === index ? -1 : index
    })
  },

  /**
   * 重试加载
   */
  onRetry() {
    this._loadHistory()
  },

  /**
   * 触底加载更多
   */
  onReachBottom() {
    this.onLoadMore()
  }
})
