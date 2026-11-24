-- Omega Overlay: puente para mGBA (0.10 o superior).
--
-- Deja que Omega Overlay lea la memoria del juego de GBA que tienes abierto.
-- Cárgalo en mGBA: Herramientas -> Scripting... -> Archivo -> Cargar script.
-- Solo escucha en este PC (127.0.0.1) y solo permite LEER memoria; no cambia nada del juego.
--
-- Protocolo (TCP, little endian):
--   petición:  u32 dirección, u32 longitud (máx. 65536)
--   respuesta: u32 longitud, y después los bytes leídos

local PORT = 45988
local MAX_LEN = 65536

local server = nil
local clients = {}
local nextId = 1

local function closeClient(id)
	local c = clients[id]
	if c then
		c.sock:close()
		clients[id] = nil
	end
end

local function handle(id)
	local c = clients[id]
	if not c then return end
	while true do
		local data, err = c.sock:receive(4096)
		if data then
			c.buf = c.buf .. data
		else
			if err ~= socket.ERRORS.AGAIN then
				closeClient(id)
				return
			end
			break
		end
	end
	while #c.buf >= 8 do
		local addr, len = string.unpack("<I4I4", c.buf)
		c.buf = c.buf:sub(9)
		local out = ""
		if len > 0 and len <= MAX_LEN and emu then
			out = emu:readRange(addr, len)
		end
		c.sock:send(string.pack("<I4", #out) .. out)
	end
end

local function accept()
	local sock, err = server:accept()
	if err or not sock then return end
	local id = nextId
	nextId = nextId + 1
	clients[id] = { sock = sock, buf = "" }
	sock:add("received", function() handle(id) end)
	sock:add("error", function() closeClient(id) end)
	console:log("Omega Overlay conectado.")
end

local err
server, err = socket.bind("127.0.0.1", PORT)
if not server then
	console:error("Omega Overlay: no se pudo abrir el puerto " .. PORT .. " (" .. tostring(err) .. "). ¿Ya estaba cargado el script?")
else
	local ok
	ok, err = server:listen()
	if err then
		server:close()
		console:error("Omega Overlay: error al escuchar en el puerto " .. PORT .. " (" .. tostring(err) .. ")")
	else
		server:add("received", accept)
		console:log("Omega Overlay listo (puerto " .. PORT .. "). Deja esta ventana abierta y abre Omega Overlay.")
	end
end
