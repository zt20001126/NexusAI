import Phaser from 'phaser'
import type { RunnerCommand, RunnerSnapshot, RunnerStatus } from '../model/gameTypes'
import { RUNNER_COMMAND_EVENT, RUNNER_STATUS_EVENT } from '../model/gameTypes'
import { GAME_HEIGHT, GAME_WIDTH } from '../model/gameConfig'

const GROUND_Y = 352
const RUNNER_X = 160
const RUNNER_FRAME_WIDTH = 543
const RUNNER_FRAME_HEIGHT = 724
const RUNNER_SCALE = 0.22
const RUNNER_BODY_WIDTH = 318
const RUNNER_BODY_HEIGHT = 590
const RUNNER_DUCK_BODY_HEIGHT = 220

/** Phaser 场景：管理跑酷物理、障碍生成、键盘输入和游戏状态。 */
export default class RunnerScene extends Phaser.Scene {
  private runner!: Phaser.Physics.Arcade.Sprite
  private obstacles!: Phaser.Physics.Arcade.Group
  private ground!: Phaser.Types.Physics.Arcade.ImageWithStaticBody
  private groundMarks: Phaser.GameObjects.Rectangle[] = []
  private runStatus: RunnerStatus = 'ready'
  private elapsedMs = 0
  private uiElapsedMs = 0
  private obstacleElapsedMs = 0
  private nextObstacleMs = 1250
  private ducking = false

  constructor() {
    super('RunnerScene')
  }

  preload() {
    this.load.spritesheet('xukun-runner', '/games/xukun-runner.png', {
      frameWidth: RUNNER_FRAME_WIDTH,
      frameHeight: RUNNER_FRAME_HEIGHT,
    })
  }

  create() {
    this.createStage()
    this.createObstacleTextures()
    this.createRunner()
    this.createObstacles()
    this.createAnimations()
    this.registerInput()
    this.game.events.on(RUNNER_COMMAND_EVENT, this.handleCommand, this)
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this.shutdown, this)
    this.emitSnapshot()
  }

  update(_time: number, delta: number) {
    if (this.runStatus !== 'running') return

    const safeDelta = Math.min(delta, 80)
    this.elapsedMs += delta
    this.uiElapsedMs += delta
    this.obstacleElapsedMs += safeDelta

    const speed = this.currentSpeed()
    this.obstacles.getChildren().forEach((child) => {
      const obstacle = child as Phaser.Physics.Arcade.Image
      if (obstacle.x < -100) {
        obstacle.destroy()
      } else {
        obstacle.setVelocityX(-speed)
      }
    })
    this.moveGroundMarks(speed, safeDelta)

    if (this.obstacleElapsedMs >= this.nextObstacleMs) {
      this.spawnObstacle(speed)
      this.obstacleElapsedMs = 0
      this.nextObstacleMs = Phaser.Math.Between(1050, 1780)
    }

    if (this.uiElapsedMs >= 100) {
      this.uiElapsedMs = 0
      this.emitSnapshot()
    }
  }

  private createStage() {
    this.add.rectangle(GAME_WIDTH / 2, GAME_HEIGHT / 2, GAME_WIDTH, GAME_HEIGHT, 0xeff6ff)
    this.add.circle(760, 96, 38, 0xffffff, 0.82)
    this.add.ellipse(176, 112, 116, 26, 0xffffff, 0.74)
    this.add.ellipse(210, 112, 75, 34, 0xffffff, 0.74)
    this.add.ellipse(682, 168, 92, 22, 0xffffff, 0.58)
    this.createSewerTunnel()

    const groundTexture = this.make.graphics({ x: 0, y: 0 })
    groundTexture.fillStyle(0xd7e5f5, 1)
    groundTexture.fillRect(0, 0, GAME_WIDTH, 24)
    groundTexture.fillStyle(0x9db6d3, 1)
    groundTexture.fillRect(0, 0, GAME_WIDTH, 3)
    groundTexture.generateTexture('xukun-ground', GAME_WIDTH, 24)
    groundTexture.destroy()

    this.ground = this.physics.add.staticImage(GAME_WIDTH / 2, GROUND_Y + 12, 'xukun-ground')
    this.ground.setDisplaySize(GAME_WIDTH, 24)
    this.ground.refreshBody()

    for (let index = 0; index < 9; index += 1) {
      this.groundMarks.push(
        this.add.rectangle(40 + index * 128, GROUND_Y + 17, 34, 3, 0xadc2dc, 0.86),
      )
    }
  }

  private createSewerTunnel() {
    const tunnel = this.add.graphics()
    tunnel.fillStyle(0xcbd9e8, 1)
    tunnel.fillRect(0, GROUND_Y + 24, GAME_WIDTH, GAME_HEIGHT - (GROUND_Y + 24))

    tunnel.fillStyle(0x91a8bf, 1)
    tunnel.fillRoundedRect(14, GROUND_Y + 10, GAME_WIDTH - 28, 112, 42)
    tunnel.fillStyle(0x34495f, 1)
    tunnel.fillRoundedRect(25, GROUND_Y + 22, GAME_WIDTH - 50, 90, 34)

    tunnel.fillStyle(0x6e8398, 0.86)
    for (let x = 150; x < GAME_WIDTH - 50; x += 180) {
      tunnel.fillRoundedRect(x, GROUND_Y + 36, 8, 58, 4)
      tunnel.fillStyle(0xc3d2df, 0.9)
      tunnel.fillCircle(x + 4, GROUND_Y + 42, 2)
      tunnel.fillStyle(0x6e8398, 0.86)
    }

    tunnel.fillStyle(0x25647c, 1)
    tunnel.fillRoundedRect(25, GROUND_Y + 70, GAME_WIDTH - 50, 50, 18)
    tunnel.fillStyle(0x8be1ed, 0.72)
    for (let x = 56; x < GAME_WIDTH - 68; x += 176) {
      tunnel.fillRoundedRect(x, GROUND_Y + 73, 42, 2, 1)
      tunnel.fillRoundedRect(x + 62, GROUND_Y + 80, 20, 2, 1)
    }
  }

  private createObstacleTextures() {
    const cactus = this.make.graphics({ x: 0, y: 0 })
    cactus.fillStyle(0x1677ff, 1)
    cactus.fillRoundedRect(21, 8, 26, 75, 10)
    cactus.fillRoundedRect(5, 35, 17, 13, 6)
    cactus.fillRoundedRect(5, 25, 12, 25, 6)
    cactus.fillRoundedRect(45, 47, 17, 13, 6)
    cactus.fillRoundedRect(50, 34, 12, 27, 6)
    cactus.generateTexture('xukun-cactus', 68, 90)
    cactus.destroy()

    const bird = this.make.graphics({ x: 0, y: 0 })
    bird.fillStyle(0x0f3b82, 1)
    bird.fillEllipse(34, 24, 43, 26)
    bird.fillEllipse(16, 21, 24, 12)
    bird.fillEllipse(51, 21, 24, 12)
    bird.fillTriangle(51, 24, 66, 28, 51, 31)
    bird.fillStyle(0x06b6d4, 1)
    bird.fillEllipse(22, 11, 25, 17)
    bird.fillEllipse(48, 11, 25, 17)
    bird.generateTexture('xukun-bird', 74, 42)
    bird.destroy()
  }

  private createRunner() {
    this.runner = this.physics.add.sprite(RUNNER_X, GROUND_Y, 'xukun-runner', 0)
    this.runner.setOrigin(0.5, 1)
    this.runner.setScale(RUNNER_SCALE)
    this.runner.setDepth(5)
    this.runner.setCollideWorldBounds(true)
    this.runner.body?.setSize(RUNNER_BODY_WIDTH, RUNNER_BODY_HEIGHT, true)
    this.physics.add.collider(this.runner, this.ground)
  }

  private createObstacles() {
    this.obstacles = this.physics.add.group({ allowGravity: false, immovable: true })
    this.physics.add.overlap(
      this.runner,
      this.obstacles,
      () => this.finishRun(),
      undefined,
      this,
    )
  }

  private createAnimations() {
    this.anims.create({
      key: 'xukun-running',
      frames: this.anims.generateFrameNumbers('xukun-runner', { start: 0, end: 3 }),
      frameRate: 11,
      repeat: -1,
    })
  }

  private registerInput() {
    const keyboard = this.input.keyboard
    if (!keyboard) return

    keyboard.on('keydown', this.handleKeyDown, this)
    keyboard.on('keyup', this.handleKeyUp, this)
  }

  private handleKeyDown(event: KeyboardEvent) {
    const target = event.target
    if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) {
      return
    }

    if (event.code === 'Escape' || event.code === 'KeyP') {
      if (event.repeat) return
      event.preventDefault()
      this.togglePause()
      return
    }

    if (target instanceof HTMLElement && target.closest('button')) return

    switch (event.code) {
      case 'Space':
      case 'ArrowUp':
        event.preventDefault()
        this.jump()
        break
      case 'ArrowDown':
        event.preventDefault()
        this.setDucking(true)
        break
      default:
        break
    }
  }

  private handleKeyUp(event: KeyboardEvent) {
    if (event.code === 'ArrowDown') this.setDucking(false)
  }

  private jump() {
    if (this.runStatus === 'ready') {
      this.startRun()
      return
    }
    if (this.runStatus === 'paused') {
      this.resumeRun()
      return
    }
    if (this.runStatus !== 'running') return

    const body = this.runner.body
    if (body && (body.blocked.down || body.touching.down)) {
      this.setDucking(false)
      this.runner.setVelocityY(-625)
    }
  }

  private setDucking(ducking: boolean) {
    if (this.runStatus !== 'running' || this.ducking === ducking) return
    const body = this.runner.body
    if (!body) return
    this.ducking = ducking
    body.setSize(RUNNER_BODY_WIDTH, ducking ? RUNNER_DUCK_BODY_HEIGHT : RUNNER_BODY_HEIGHT, true)
    this.runner.setScale(RUNNER_SCALE, ducking ? RUNNER_SCALE * 0.68 : RUNNER_SCALE)
    if (ducking && !(body.blocked.down || body.touching.down)) {
      this.runner.setVelocityY(780)
    }
  }

  private handleCommand(command: RunnerCommand) {
    switch (command) {
      case 'start':
        if (this.runStatus === 'ready') this.startRun()
        break
      case 'pause':
        this.pauseRun()
        break
      case 'resume':
        this.resumeRun()
        break
      case 'restart':
        this.startRun(true)
        break
      default:
        break
    }
  }

  private startRun(restart = false) {
    if (restart) {
      this.obstacles.clear(true, true)
      this.runner.setPosition(RUNNER_X, GROUND_Y)
      this.runner.setVelocity(0, 0)
      this.runner.setScale(RUNNER_SCALE)
      this.runner.body?.setSize(RUNNER_BODY_WIDTH, RUNNER_BODY_HEIGHT, true)
      this.elapsedMs = 0
      this.uiElapsedMs = 0
      this.obstacleElapsedMs = 0
      this.nextObstacleMs = 1250
    }

    this.ducking = false
    this.physics.world.resume()
    this.runStatus = 'running'
    this.runner.play('xukun-running')
    this.emitSnapshot()
  }

  private pauseRun() {
    if (this.runStatus !== 'running') return
    this.ducking = false
    this.runner.body?.setSize(RUNNER_BODY_WIDTH, RUNNER_BODY_HEIGHT, true)
    this.runner.setScale(RUNNER_SCALE)
    this.runStatus = 'paused'
    this.physics.world.pause()
    this.runner.anims.pause()
    this.emitSnapshot()
  }

  private resumeRun() {
    if (this.runStatus !== 'paused') return
    this.physics.world.resume()
    this.runStatus = 'running'
    this.runner.anims.resume()
    this.emitSnapshot()
  }

  private togglePause() {
    if (this.runStatus === 'running') this.pauseRun()
    else if (this.runStatus === 'paused') this.resumeRun()
    else if (this.runStatus === 'ready') this.startRun()
  }

  private finishRun() {
    if (this.runStatus !== 'running') return
    if (this.ducking) this.setDucking(false)
    this.runStatus = 'gameover'
    this.physics.world.pause()
    this.runner.anims.stop()
    this.emitSnapshot()
  }

  private spawnObstacle(speed: number) {
    const isBird = Phaser.Math.Between(0, 4) === 0 && this.elapsedMs > 5000
    const obstacle = this.physics.add.image(
      GAME_WIDTH + 60,
      isBird ? GROUND_Y - Phaser.Math.Between(70, 112) : GROUND_Y,
      isBird ? 'xukun-bird' : 'xukun-cactus',
    )
    obstacle.setOrigin(0.5, isBird ? 0.5 : 1)
    obstacle.setDisplaySize(isBird ? 72 : 54, isBird ? 42 : 72)
    obstacle.setImmovable(true)
    obstacle.body.setAllowGravity(false)
    obstacle.setVelocityX(-speed)
    this.obstacles.add(obstacle)
  }

  private currentSpeed() {
    return Math.min(650, 375 + (this.elapsedMs / 1000) * 4.3)
  }

  private moveGroundMarks(speed: number, delta: number) {
    this.groundMarks.forEach((mark) => {
      mark.x -= speed * delta / 1000
      if (mark.x < -24) mark.x = GAME_WIDTH + 20
    })
  }

  private emitSnapshot() {
    const snapshot: RunnerSnapshot = { status: this.runStatus, elapsedMs: this.elapsedMs }
    this.game.events.emit(RUNNER_STATUS_EVENT, snapshot)
  }

  private shutdown() {
    this.game.events.off(RUNNER_COMMAND_EVENT, this.handleCommand, this)
    this.input.keyboard?.off('keydown', this.handleKeyDown, this)
    this.input.keyboard?.off('keyup', this.handleKeyUp, this)
  }
}
