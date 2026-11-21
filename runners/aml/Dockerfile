FROM node:24-alpine

WORKDIR /app
COPY adapter.mjs server.mjs ./

ENV PORT=8790
EXPOSE 8790
CMD ["node", "server.mjs"]
