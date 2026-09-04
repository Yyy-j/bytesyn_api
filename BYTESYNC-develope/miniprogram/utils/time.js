// utils/time.js — 时间工具

/**
 * 获取当前日期字符串 YYYY-MM-DD
 */
const getCurrentDate = () => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 获取当前时间字符串 HH:mm
 */
const getCurrentTime = () => {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${min}`
}

/**
 * 获取昨天日期字符串 YYYY-MM-DD（本地时间，非 UTC）
 */
const getYesterdayDate = () => {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

module.exports = { getCurrentDate, getCurrentTime, getYesterdayDate }
