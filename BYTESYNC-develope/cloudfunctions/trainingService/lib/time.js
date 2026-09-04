// cloudfunctions/trainingService/lib/time.js — 训练日期和周次工具（云端版本）
// 与前端 training-time.js 保持一致的日期计算逻辑
// 统一使用 Asia/Tokyo 时区，不依赖运行环境默认时区

/**
 * 训练业务时区
 * 所有日期计算均按此时区执行
 */
const TRAINING_TIME_ZONE = 'Asia/Tokyo'

/**
 * 将 Date 对象转换为指定时区的日期组件
 * @param {Date} date - Date 对象
 * @returns {Object} { year, month, day, hour, dayOfWeek }
 */
const getDateInTimeZone = (date = new Date()) => {
  // 使用 Intl.DateTimeFormat 获取时区内的日期组件
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: TRAINING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
    hour: '2-digit',
    hour12: false
  })
  
  const parts = formatter.formatToParts(date)
  const get = (type) => parts.find(p => p.type === type)?.value
  
  const weekdayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }
  
  return {
    year: parseInt(get('year'), 10),
    month: parseInt(get('month'), 10),
    day: parseInt(get('day'), 10),
    hour: parseInt(get('hour'), 10),
    dayOfWeek: weekdayMap[get('weekday')] ?? 0
  }
}

/**
 * 获取日期字符串（YYYY-MM-DD）
 * 按 Asia/Tokyo 时区计算
 * @param {Date} [date] - Date 对象，默认当前时间
 * @returns {string} 格式化的日期字符串
 */
const formatLocalDate = (date = new Date()) => {
  const { year, month, day } = getDateInTimeZone(date)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/**
 * 解析日期字符串为 UTC 时间的 Date 对象
 * @param {string} dateStr - YYYY-MM-DD 格式的日期字符串
 * @returns {Date} Date 对象（UTC 0点）
 */
const parseLocalDate = (dateStr) => {
  const [y, m, d] = dateStr.split('-').map(Number)
  // 使用 UTC 避免时区问题
  return new Date(Date.UTC(y, m - 1, d))
}

/**
 * 计算某年有多少个 ISO 周
 * @param {number} year - 年份
 * @returns {number} 52 或 53
 */
const getISOWeeksInYear = (year) => {
  // 该年12月28日一定在最后一周
  const dec28 = new Date(Date.UTC(year, 11, 28))
  const dayOfWeek = dec28.getUTCDay() || 7
  dec28.setUTCDate(dec28.getUTCDate() + 4 - dayOfWeek)
  const yearStart = new Date(Date.UTC(dec28.getUTCFullYear(), 0, 1))
  const daysDiff = Math.floor((dec28 - yearStart) / (24 * 60 * 60 * 1000))
  return Math.ceil((daysDiff + 1) / 7)
}

/**
 * 获取 ISO 周标识
 * 格式：YYYY-Www（如 2026-W28）
 * 遵循 ISO 8601：周一为一周第一天，每年第一周包含该年第一个周四
 * 按 Asia/Tokyo 时区计算
 * @param {Date} [date] - Date 对象，默认当前时间
 * @returns {string} 周标识字符串
 */
const getWeekId = (date = new Date()) => {
  // 获取 Asia/Tokyo 时区的日期组件
  const { year, month, day, dayOfWeek } = getDateInTimeZone(date)
  
  // 创建 UTC 日期用于计算
  const target = new Date(Date.UTC(year, month - 1, day))
  
  // ISO 周：周一=1, 周日=7
  const isoDay = dayOfWeek === 0 ? 7 : dayOfWeek
  
  // 调整到本周四（ISO 周的参考日）
  target.setUTCDate(target.getUTCDate() + 4 - isoDay)
  
  // 获取该周四所在年份的第一天
  const isoYear = target.getUTCFullYear()
  const yearStart = new Date(Date.UTC(isoYear, 0, 1))
  
  // 计算周四距离年初的天数，然后计算周次
  const daysDiff = Math.floor((target - yearStart) / (24 * 60 * 60 * 1000))
  const weekNum = Math.ceil((daysDiff + 1) / 7)
  
  return `${isoYear}-W${String(weekNum).padStart(2, '0')}`
}

/**
 * 根据周标识获取该周周一的日期
 * @param {string} weekId - 周标识，格式 YYYY-Www
 * @returns {string} 周一日期，格式 YYYY-MM-DD
 */
const getWeekStartDate = (weekId) => {
  // 解析周标识
  const match = weekId.match(/^(\d{4})-W(\d{2})$/)
  if (!match) {
    throw new Error('无效的周标识格式，应为 YYYY-Www')
  }
  
  const year = parseInt(match[1], 10)
  const week = parseInt(match[2], 10)
  
  // 找到该年 1 月 4 日（一定在第 1 周）
  const jan4 = new Date(Date.UTC(year, 0, 4))
  
  // 获取 1 月 4 日是周几（ISO：周一=1, 周日=7）
  const jan4Day = jan4.getUTCDay() || 7
  
  // 计算第 1 周的周一
  const week1Monday = new Date(jan4)
  week1Monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1)
  
  // 计算目标周的周一
  const targetMonday = new Date(week1Monday)
  targetMonday.setUTCDate(week1Monday.getUTCDate() + (week - 1) * 7)
  
  // 格式化输出
  const y = targetMonday.getUTCFullYear()
  const m = String(targetMonday.getUTCMonth() + 1).padStart(2, '0')
  const d = String(targetMonday.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 根据周标识获取该周周日的日期
 * @param {string} weekId - 周标识，格式 YYYY-Www
 * @returns {string} 周日日期，格式 YYYY-MM-DD
 */
const getWeekEndDate = (weekId) => {
  const mondayStr = getWeekStartDate(weekId)
  const [y, m, d] = mondayStr.split('-').map(Number)
  const monday = new Date(Date.UTC(y, m - 1, d))
  const sunday = new Date(monday)
  sunday.setUTCDate(monday.getUTCDate() + 6)
  
  const sy = sunday.getUTCFullYear()
  const sm = String(sunday.getUTCMonth() + 1).padStart(2, '0')
  const sd = String(sunday.getUTCDate()).padStart(2, '0')
  return `${sy}-${sm}-${sd}`
}

/**
 * 获取一周中每天的日期数组
 * @param {string} weekId - 周标识，格式 YYYY-Www
 * @returns {Array<string>} 包含 7 个日期字符串的数组，从周一到周日
 */
const getWeekDates = (weekId) => {
  const mondayStr = getWeekStartDate(weekId)
  const [y, m, d] = mondayStr.split('-').map(Number)
  const monday = new Date(Date.UTC(y, m - 1, d))
  
  const dates = []
  for (let i = 0; i < 7; i++) {
    const day = new Date(monday)
    day.setUTCDate(monday.getUTCDate() + i)
    const dy = day.getUTCFullYear()
    const dm = String(day.getUTCMonth() + 1).padStart(2, '0')
    const dd = String(day.getUTCDate()).padStart(2, '0')
    dates.push(`${dy}-${dm}-${dd}`)
  }
  
  return dates
}

/**
 * 验证周标识格式是否正确且该周实际存在
 * @param {string} weekId - 周标识
 * @returns {boolean} 是否为有效的周标识
 */
const isValidWeekId = (weekId) => {
  if (!weekId || typeof weekId !== 'string') {
    return false
  }
  const match = weekId.match(/^(\d{4})-W(\d{2})$/)
  if (!match) {
    return false
  }
  const year = parseInt(match[1], 10)
  const week = parseInt(match[2], 10)
  
  // 基本范围检查
  if (week < 1 || week > 53) {
    return false
  }
  
  // 检查该年份是否真的有第53周
  if (week === 53) {
    const maxWeeks = getISOWeeksInYear(year)
    if (maxWeeks < 53) {
      return false
    }
  }
  
  return true
}

module.exports = {
  TRAINING_TIME_ZONE,
  getDateInTimeZone,
  formatLocalDate,
  parseLocalDate,
  getISOWeeksInYear,
  getWeekId,
  getWeekStartDate,
  getWeekEndDate,
  getWeekDates,
  isValidWeekId
}
