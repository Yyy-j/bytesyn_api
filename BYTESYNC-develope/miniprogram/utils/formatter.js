// utils/formatter.js — 数据展示格式化工具

const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六']

/**
 * 格式化 Date 为 YYYY-MM-DD 字符串
 */
const formatDate = (date = new Date()) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 格式化日期字符串为中文展示，如「5月19日 周一」
 */
const formatDateCN = (dateStr) => {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}月${d.getDate()}日 周${WEEK_CN[d.getDay()]}`
}

/**
 * 数字保留 n 位小数
 */
const toFixed = (num, n = 1) => Number(num).toFixed(n)

module.exports = { formatDate, formatDateCN, toFixed }
