const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 4000;

// Proxy API calls to chatbot service
app.use('/api', createProxyMiddleware({
  target: 'http://chatbot:8000',
  changeOrigin: true,
  pathRewrite: {
    '^/api': '',
  },
}));

// Serve static files
app.use(express.static(path.join(__dirname, 'dist/website/browser')));
// Serve settings files
app.use('/settings', express.static(path.join(__dirname, 'settings')));

// Handle Angular routing
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'dist/website/browser/index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});