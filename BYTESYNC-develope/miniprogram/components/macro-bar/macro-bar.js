// components/macro-bar/macro-bar.js
const { calcPct } = require('../../utils/nutrition')

Component({
  properties: {
    protein:     { type: Number, value: 0  },
    carbs:       { type: Number, value: 0  },
    fat:         { type: Number, value: 0  },
    proteinGoal: { type: Number, value: 60 },
    carbsGoal:   { type: Number, value: 250 },
    fatGoal:     { type: Number, value: 65 }
  },

  data: {
    proteinPct: 0,
    carbsPct:   0,
    fatPct:     0
  },

  observers: {
    'protein, proteinGoal, carbs, carbsGoal, fat, fatGoal'() {
      const { protein, proteinGoal, carbs, carbsGoal, fat, fatGoal } = this.data
      this.setData({
        proteinPct: calcPct(protein, proteinGoal),
        carbsPct:   calcPct(carbs,   carbsGoal),
        fatPct:     calcPct(fat,     fatGoal)
      })
    }
  },

  methods: {}
})
