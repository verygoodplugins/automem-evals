import { createAmlAdapterServer } from './adapter.mjs';

const port = Number(process.env.PORT || 8790);
const server = createAmlAdapterServer({
  automemUrl: process.env.AUTOMEM_API_URL,
  automemApiKey: process.env.AUTOMEM_API_KEY,
  adapterApiKey: process.env.AML_ADAPTER_API_KEY,
});

server.listen(port, '0.0.0.0', () => {
  process.stderr.write(`AutoMem AML adapter listening on ${port}\n`);
});

const shutdown = () => server.close(() => process.exit(0));
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
