// components/date-switcher/date-switcher.js
const { formatDateCN } = require('../../utils/formatter')

Component({
  properties: {
    date: { type: String, value: '' }
  },

  data: {
    displayDate: ''
  },

  observers: {
    date(val) {
      this.setData({ displayDate: val ? formatDateCN(val) : '' })
    }
  },

  methods: {
    onPrev() {
      this.triggerEvent('change', { direction: -1 })
    },
    onNext() {
      this.triggerEvent('change', { direction: 1 })
    }
  }
})
