# gta-heist-closer

Closes GTA when it detects the Heist Passed screen for Cayo Perico.

## Usage

Download the latest release binary and run it. It will ask you for admin rights, this is required to use some
shell commands for disabling the network .

## Known Issues

- The `Disable Network` option does not always work properly. It seems that recently, Rockstar has been updating the
  game to prevent this from working. I have not found a way to get around this yet. If you see a message
  saying `SAVING FAILED` in-game, this means nothing. It is still entirely possible you are connected to the server. The
  only 100% way to know is if the game kicks you back to story mode. This means it worked.
- The image resizing can be funky if you play in windowed mode. To this, I say "why the hell are you playing in windowed
  mode?"
