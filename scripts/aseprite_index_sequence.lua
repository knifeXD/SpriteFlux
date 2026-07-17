-- SpriteFlux Aseprite adapter: convert one fixed-grid RGBA sequence to
-- Indexed mode with a caller-supplied shared palette and no dithering.

local inputDir = app.params["inputDir"]
local outputDir = app.params["outputDir"]
local paletteFile = app.params["paletteFile"]
local frameCount = tonumber(app.params["frameCount"])
local canvasWidth = tonumber(app.params["canvasWidth"])
local canvasHeight = tonumber(app.params["canvasHeight"])
local artFps = tonumber(app.params["artFps"] or "24")

if not inputDir or not outputDir or not paletteFile or
   not frameCount or not canvasWidth or not canvasHeight then
  error("inputDir, outputDir, paletteFile, frameCount, canvasWidth, and canvasHeight are required")
end

local sprite = Sprite(canvasWidth, canvasHeight, ColorMode.RGB)
local layer = sprite.layers[1]
layer.name = "Beauty"

for index = 0, frameCount - 1 do
  local source = string.format("%s/frame-%04d.png", inputDir, index)
  local image = Image{ fromFile=source }
  if image.width ~= canvasWidth or image.height ~= canvasHeight then
    error("Unexpected input canvas: " .. source)
  end
  if index == 0 then
    sprite.cels[1].image:drawImage(image, Point(0, 0))
  else
    sprite:newEmptyFrame()
    sprite:newCel(layer, index + 1, image, Point(0, 0))
  end
  sprite.frames[index + 1].duration = 1.0 / artFps
end

app.activeSprite = sprite
sprite:setPalette(Palette{ fromFile=paletteFile })
app.command.ChangePixelFormat{
  format="indexed",
  dithering="none",
  rgbmap="octree"
}

sprite:saveAs(outputDir .. "/sequence.aseprite")
local palette = sprite.palettes[1]
for index = 0, frameCount - 1 do
  local target = string.format("%s/beauty/frame-%04d.png", outputDir, index)
  sprite.cels[index + 1].image:saveAs{ filename=target, palette=palette }
end

sprite:close()
