// Disassemble (following flow) then decompile the X-Pro3 handshake functions.
// Run: analyzeHeadless PROJ NAME -process ffboot.bin -noanalysis \
//        -scriptPath DIR -postScript Xpro3Decompile3.java
import java.io.PrintWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;

public class Xpro3Decompile3 extends GhidraScript {

	private static final long[] TARGETS = {
		0x10907ACL, 0x1090AFCL, 0x1090BECL, 0x1090BA8L, 0x1090E68L,
		0x10973DCL, 0x1097140L, 0x1092AD0L, 0x1090E34L, 0x1090C0CL,
		0x114FC44L, 0x57B74L, 0x4E998L, 0x11500F4L, 0x1150004L,
		0x11501BCL, 0x516F0L, 0x4A94CL, 0x1150210L, 0x114F798L,
		0x4C1E0L, 0x1092CD8L, 0x1092CB8L, 0x1090F70L, 0x1091350L,
	};

	@Override
	protected void run() throws Exception {
		String out = System.getenv("XPRO3_OUT");
		if (out == null) {
			out = "/tmp/opencode";
		}
		String path = out + "/xpro3_decompile3.txt";
		ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();

		int ok = 0;
		for (long target : TARGETS) {
			Address start = toAddr(target);
			try {
				AddressSet body = new AddressSet(start, toAddr(target + 0x400));
				DisassembleCommand command = new DisassembleCommand(body, null, true);
				command.applyTo(currentProgram, monitor);
				ok++;
			} catch (Exception e) {
				println("disassemble failed at " + start + ": " + e.getMessage());
			}
		}
		println("disassembled " + ok + " of " + TARGETS.length + " ranges");

		DecompInterface decompiler = new DecompInterface();
		decompiler.openProgram(currentProgram);

		try (PrintWriter writer = new PrintWriter(path)) {
			writer.println("# program: " + currentProgram.getName());
			for (long target : TARGETS) {
				Address address = toAddr(target);
				writer.println();
				writer.println("==============================================================================");
				writer.printf("## 0x%08x%n", target);
				writer.println("==============================================================================");
				Function function = getFunctionAt(address);
				if (function == null) {
					function = createFunction(address, null);
				}
				if (function == null) {
					writer.println("(no function)");
					continue;
				}
				DecompileResults results = decompiler.decompileFunction(function, 120, monitor);
				if (!results.decompileCompleted()) {
					writer.println("(failed: " + results.getErrorMessage() + ")");
					continue;
				}
				writer.println(results.getDecompiledFunction().getC());
			}
		}
		println("written " + path);
	}
}