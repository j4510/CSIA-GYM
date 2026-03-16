// Interactive Neuron-inspired Background
// Responsive to cursor position for a modern, fluid effect

document.addEventListener('DOMContentLoaded', () => {
    initializeInteractiveBackground();
});

function initializeInteractiveBackground() {
    const canvas = document.createElement('canvas');
    canvas.className = 'neuron-canvas';
    canvas.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: -1;
        opacity: 0.15;
    `;
    document.body.insertBefore(canvas, document.body.firstChild);

    const ctx = canvas.getContext('2d');
    const nodes = [];
    const mouse = { x: 0, y: 0 };

    // Set canvas size
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        initNodes();
    }

    // Create neuron nodes
    function initNodes() {
        nodes.length = 0;
        const nodeCount = Math.min(Math.floor((canvas.width * canvas.height) / 25000), 20);
        
        for (let i = 0; i < nodeCount; i++) {
            nodes.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                radius: Math.random() * 2 + 1.5,
                originalX: 0,
                originalY: 0
            });
            
            nodes[i].originalX = nodes[i].x;
            nodes[i].originalY = nodes[i].y;
        }
    }

    // Draw nodes and connections
    function draw() {
        ctx.fillStyle = 'rgba(139, 0, 0, 0.08)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw connections
        ctx.strokeStyle = 'rgba(139, 0, 0, 0.1)';
        ctx.lineWidth = 0.5;

        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < 200) {
                    const alpha = Math.max(0, 1 - distance / 200);
                    ctx.strokeStyle = `rgba(139, 0, 0, ${alpha * 0.1})`;
                    ctx.beginPath();
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                    ctx.stroke();
                }
            }
        }

        // Draw nodes
        for (let i = 0; i < nodes.length; i++) {
            // Calculate attraction to mouse
            const dx = mouse.x - nodes[i].x;
            const dy = mouse.y - nodes[i].y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < 300) {
                const force = (1 - distance / 300) * 0.02;
                nodes[i].vx += (dx / distance) * force;
                nodes[i].vy += (dy / distance) * force;
            }

            // Apply damping (return to original position)
            const returnForce = 0.92;
            nodes[i].vx += (nodes[i].originalX - nodes[i].x) * 0.0005;
            nodes[i].vy += (nodes[i].originalY - nodes[i].y) * 0.0005;
            nodes[i].vx *= returnForce;
            nodes[i].vy *= returnForce;

            // Update position
            nodes[i].x += nodes[i].vx;
            nodes[i].y += nodes[i].vy;

            // Boundary wrapping
            if (nodes[i].x < 0) nodes[i].x = canvas.width;
            if (nodes[i].x > canvas.width) nodes[i].x = 0;
            if (nodes[i].y < 0) nodes[i].y = canvas.height;
            if (nodes[i].y > canvas.height) nodes[i].y = 0;

            // Draw node with glow
            const nodeAlpha = Math.min(0.4, (1 - Math.abs(nodes[i].vx) - Math.abs(nodes[i].vy)) * 0.5);
            
            ctx.fillStyle = `rgba(139, 0, 0, ${nodeAlpha})`;
            ctx.beginPath();
            ctx.arc(nodes[i].x, nodes[i].y, nodes[i].radius, 0, Math.PI * 2);
            ctx.fill();

            // Subtle glow
            ctx.fillStyle = `rgba(139, 0, 0, ${nodeAlpha * 0.3})`;
            ctx.beginPath();
            ctx.arc(nodes[i].x, nodes[i].y, nodes[i].radius * 1.5, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    // Animation loop
    function animate() {
        draw();
        requestAnimationFrame(animate);
    }

    // Track mouse position
    document.addEventListener('mousemove', (e) => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    });

    // Reset on mouse leave
    document.addEventListener('mouseleave', () => {
        mouse.x = canvas.width / 2;
        mouse.y = canvas.height / 2;
    });

    // Handle window resize
    window.addEventListener('resize', resizeCanvas);

    // Initialize
    resizeCanvas();
    animate();
}

// Smooth scroll behavior enhancement
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href !== '#' && document.querySelector(href)) {
            e.preventDefault();
            document.querySelector(href).scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Prevent button glitching by disabling pointer events during animations
document.addEventListener('mousedown', (e) => {
    if (e.target.matches('button, .btn, input[type="submit"], a.bg-red-600')) {
        e.target.style.pointerEvents = 'none';
        setTimeout(() => {
            e.target.style.pointerEvents = 'auto';
        }, 300);
    }
});

// Smooth focus management
document.addEventListener('focusin', (e) => {
    if (e.target.matches('input, textarea, select')) {
        e.target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});
