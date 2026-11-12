// The Jetson serves a SPA through Nginx. Other builds retain app.json's output.
module.exports = ({ config }) => {
  const output = process.env.WORDRECALL_WEB_OUTPUT;
  if (output && !['single', 'static', 'server'].includes(output)) {
    throw new Error('WORDRECALL_WEB_OUTPUT must be single, static, or server');
  }
  return {
    ...config,
    web: { ...config.web, ...(output ? { output } : {}) },
  };
};
