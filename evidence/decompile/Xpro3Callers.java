// Decompile the callers of the transfer entry points to find who passes the
// "progress callback" flag (param_1 == 1) to FUN_01090afc / FUN_01090f70.
import java.io.PrintWriter;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;

public class Xpro3Callers extends GhidraScript {

	// BL sites measured to call FUN_01090afc, FUN_01090f70, FUN_01090c0c, FUN_010907ac
	private static final long[] TARGETS = {
		0x1090F70L, 0x10910B4L, 0x10911D8L, 0x1090C0CL, 0x1091254L,
		0x1091000L, 0x1091098L, 0x10911A0L, 0x1090E34L, 0x1091350L,
		0x1090D10L, 0x1091A58L, 0x1091BDCL, 0x1091C00L, 0x1099324L,
	};

	@Override
	protected void run() throws Exception {
		String out = System.getenv("XPRO3_OUT");
		if (out == null) {
			out = "/tmp/opencode";
		}
		String path = out + "/xpro3_callers.txt";
		ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();

		for (long target : TARGETS) {
			Address start = toAddr(target);
			try {
				DisassembleCommand command =
					new DisassembleCommand(new AddressSet(start, toAddr(target + 0x300)), null, true);
				command.applyTo(currentProgram, monitor);
			} catch (Exception e) {
				println("disassemble failed at " + start);
			}
		}

		DecompInterface decompiler = new DecompInterface();
		decompiler.openProgram(currentProgram);
		try (PrintWriter writer = new PrintWriter(path)) {
			writer.println("# callers of the X-Pro3 transfer engine");
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