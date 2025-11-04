// middleware/auth.js
const jwt = require('jsonwebtoken');

// Expect Authorization: Bearer <token>
module.exports = function auth(req, res, next) {
  const h = req.headers.authorization || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : null;
  if (!token) return res.status(401).json({ message: 'Unauthorized' });

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    req.user = { id: payload.sub }; // store user id
    next();
  } catch {
    return res.status(401).json({ message: 'Invalid token' });
  }
};
