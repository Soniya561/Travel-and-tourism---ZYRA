// models/Boundary.js
const mongoose = require('mongoose');

const boundarySchema = new mongoose.Schema({
  name: String,
  // Use Polygon for flexibility. You can also store center+radius if you prefer.
  area: {
    type: { type: String, enum: ['Polygon'], required: true },
    coordinates: { type: [[[Number]]], required: true } // GeoJSON polygon
  },
  active: { type: Boolean, default: true }
});

module.exports = mongoose.model('Boundary', boundarySchema);
