FROM node:20-alpine

WORKDIR /app
# IMPORTANT: paths are relative to the build context (./web)
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

EXPOSE 3001
CMD ["npm", "run", "dev", "--", "-p", "3001"]
