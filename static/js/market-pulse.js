/* static/js/market-pulse.js */
class MarketPulse {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.svg = this.container.querySelector('.market-pulse-svg');
    this.scoreEl = this.container.querySelector('.market-pulse-score');
    this.deltaEl = this.container.querySelector('.market-pulse-delta');
    this.speed = options.speed || 0.02;
    this.particleCount = options.particleCount || 20;
    this.particles = [];
    this.score = options.initialScore || 50;
    this.animationFrameId = null;

    this.init();
    this.animate();
  }

  init() {
    // Create particles
    for (let i = 0; i < this.particleCount; i++) {
      this.particles.push({
        x: Math.random() * 100,
        y: Math.random() * 100,
        radius: Math.random() * 2 + 1,
        speedX: (Math.random() - 0.5) * this.speed * 10,
        speedY: (Math.random() - 0.5) * this.speed * 10,
        opacity: Math.random() * 0.6 + 0.2
      });
    }

    // Create SVG elements that we'll update rather than recreate
    this.particleElements = [];
    for (let i = 0; i < this.particleCount; i++) {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('fill', `var(--color-accent)`);
      this.svg.appendChild(circle);
      this.particleElements.push(circle);
    }

    // Create track element
    this.trackElement = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    this.trackElement.setAttribute('fill', 'none');
    this.trackElement.setAttribute('stroke', `var(--color-accent-track)`);
    this.trackElement.setAttribute('stroke-width', '8');
    this.svg.appendChild(this.trackElement);

    // Create arc element
    this.arcElement = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    this.arcElement.setAttribute('fill', 'none');
    this.arcElement.setAttribute('stroke', `var(--color-accent)`);
    this.arcElement.setAttribute('stroke-width', '6');
    this.arcElement.setAttribute('stroke-linecap', 'round');
    this.svg.appendChild(this.arcElement);

    // Initial render
    this.render();
  }

  updateScore(score, delta) {
    this.score = Math.max(0, Math.min(100, score));
    this.scoreEl.textContent = this.score;
    this.deltaEl.textContent = delta >= 0 ? `▲ ${delta}` : `▼ ${Math.abs(delta)}`;
    this.deltaEl.className = `market-pulse-delta ${delta >= 0 ? 'positive' : 'negative'}`;

    // Adjust particle speed based on score (more energy = faster movement)
    // Preserve direction and adjust magnitude proportionally to avoid jerkiness
    const speedFactor = 0.5 + (this.score / 100) * 1.5;
    this.particles.forEach(p => {
      // Calculate current speed magnitude
      const currentSpeedX = Math.abs(p.speedX);
      const currentSpeedY = Math.abs(p.speedY);

      // Avoid division by zero
      const speedX = currentSpeedX > 0 ? currentSpeedX : 0.1;
      const speedY = currentSpeedY > 0 ? currentSpeedY : 0.1;

      // Adjust speed proportionally, preserving direction
      p.speedX = (p.speedX / speedX) * speedX * speedFactor * 0.5;
      p.speedY = (p.speedY / speedY) * speedY * speedFactor * 0.5;
    });

    // Dispatch custom event for external listeners
    this.container.dispatchEvent(new CustomEvent('market-pulse-update', {
      detail: { score: this.score, delta: delta }
    }));
  }

  render() {
    // Update particles
    this.particles.forEach((p, index) => {
      const circle = this.particleElements[index];
      circle.setAttribute('cx', p.x);
      circle.setAttribute('cy', p.y);
      circle.setAttribute('r', p.radius);
      circle.setAttribute('opacity', p.opacity);
    });

    // Update track
    this.trackElement.setAttribute('cx', '60');
    this.trackElement.setAttribute('cy', '60');
    this.trackElement.setAttribute('r', '50');

    // Update score arc (progress indicator)
    const endAngle = (this.score / 100) * 2 * Math.PI;
    const largeArc = this.score > 50 ? '1' : '0';
    const d = `
      M 60,10
      A 50,50 0 ${largeArc} 1
      ${60 + 50 * Math.sin(endAngle)},${60 - 50 * Math.cos(endAngle)}
    `;
    this.arcElement.setAttribute('d', d.trim());
  }

  animate() {
    // Update particle positions
    this.particles.forEach(p => {
      p.x += p.speedX;
      p.y += p.speedY;

      // Wrap around boundaries using actual SVG dimensions
      const svgWidth = this.svg.width.baseVal.value || this.svg.viewBox.baseVal.width || 120;
      const svgHeight = this.svg.height.baseVal.value || this.svg.viewBox.baseVal.height || 120;

      if (p.x < 0) p.x = svgWidth;
      if (p.x > svgWidth) p.x = 0;
      if (p.y < 0) p.y = svgHeight;
      if (p.y > svgHeight) p.y = 0;
    });

    this.render();
    this.animationFrameId = requestAnimationFrame(() => this.animate());
  }

  /**
   * Clean up animation frame to prevent memory leaks
   */
  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }
}

// Auto-initialize if element exists
document.addEventListener('DOMContentLoaded', () => {
  const pulseContainer = document.getElementById('market-pulse');
  if (pulseContainer) {
    // Would normally get initial score from data attribute or JS
    // For now, initialize with sample data
    const initialScore = pulseContainer.getAttribute('data-initial-score') || 65;
    new MarketPulse('market-pulse', {
      initialScore: parseInt(initialScore),
      speed: 0.015
    });
  }
});